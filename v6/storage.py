"""Durable queue with fail-closed publishing and long-lived hashed dedupe tombstones.

Google review content and identifiable resource paths are purged after 29 days;
only an irreversible SHA-256 tombstone is retained to avoid reposting old reviews.
"""
import hashlib
import os
import sqlite3
import time
from contextlib import contextmanager

from core import UNCERTAIN_WRITE_ERROR

# PostgreSQL REAL is float4 (about 128s spacing near today's epoch); use float8 for deadlines.
SCHEMA = '''CREATE TABLE IF NOT EXISTS review_jobs (
    review_name TEXT PRIMARY KEY,
    location_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_try DOUBLE PRECISION NOT NULL DEFAULT 0,
    lease_until DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_error TEXT,
    reply_text TEXT,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);'''
TOMBSTONE_SCHEMA = '''CREATE TABLE IF NOT EXISTS review_tombstones (
    review_hash TEXT PRIMARY KEY,
    prior_status TEXT NOT NULL
);'''
COUNTER_SCHEMA = '''CREATE TABLE IF NOT EXISTS audit_counters (
    name TEXT PRIMARY KEY,
    amount INTEGER NOT NULL DEFAULT 0
);'''


def _digest(resource):
    return hashlib.sha256(resource.encode('utf-8')).hexdigest()


class Store:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or os.environ.get('DATABASE_URL', '')
        self.is_postgres = self.dsn.startswith(('postgres://', 'postgresql://'))
        if not self.is_postgres and not (self.dsn.startswith('sqlite:') and os.getenv('ALLOW_SQLITE_DEV') == 'true'):
            raise RuntimeError('Production requires durable Postgres; SQLite for explicit development only')
        self.init()

    def _sql(self, query):
        return query if self.is_postgres else query.replace('%s', '?')

    @contextmanager
    def connection(self):
        if self.is_postgres:
            import psycopg
            db = psycopg.connect(self.dsn, connect_timeout=10)
        else:
            db = sqlite3.connect(self.dsn.removeprefix('sqlite:'), timeout=15, isolation_level=None)
            db.execute('PRAGMA busy_timeout=15000')
            db.execute('PRAGMA journal_mode=WAL')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def init(self):
        with self.connection() as db:
            db.execute(SCHEMA)
            db.execute(TOMBSTONE_SCHEMA)
            db.execute(COUNTER_SCHEMA)
            db.execute('CREATE INDEX IF NOT EXISTS review_jobs_due_idx ON review_jobs(status, next_try, lease_until)')

    def enqueue(self, event) -> bool:
        now = time.time()
        with self.connection() as db:
            if not self.is_postgres:
                db.execute('BEGIN IMMEDIATE')
            exists = db.execute(self._sql('SELECT 1 FROM review_tombstones WHERE review_hash=%s'),
                                (_digest(event.review_name),)).fetchone()
            if exists:
                # Only an explicitly requested official backfill may revisit an
                # expired unresolved review. Completed reviews stay immutable.
                prior = db.execute(self._sql('SELECT prior_status FROM review_tombstones WHERE review_hash=%s'),
                                   (_digest(event.review_name),)).fetchone()
                if event.event_type != 'BACKFILL' or prior[0] != 'expired':
                    return False
                db.execute(self._sql('DELETE FROM review_tombstones WHERE review_hash=%s'),
                           (_digest(event.review_name),))
            result = db.execute(self._sql('''INSERT INTO review_jobs
                (review_name,location_name,event_type,status,next_try,created_at,updated_at)
                VALUES (%s,%s,%s,'queued',%s,%s,%s)
                ON CONFLICT(review_name) DO NOTHING'''),
                (event.review_name, event.location_name, event.event_type, now, now, now))
            return result.rowcount == 1

    def claim(self, review_name: str | None = None):
        now = time.time()
        with self.connection() as db:
            if not self.is_postgres:
                db.execute('BEGIN IMMEDIATE')
            conditions = ("((status IN ('queued','retry','verify_pending') AND next_try <= %s) "
                          "OR (status IN ('processing','write_intent') AND lease_until < %s))")
            args = [now, now]
            if review_name:
                conditions += ' AND review_name=%s'
                args.append(review_name)
            query = ('SELECT review_name,location_name,attempts,status,reply_text,event_type FROM review_jobs WHERE ' +
                     conditions + ' ORDER BY created_at LIMIT 1' +
                     (' FOR UPDATE SKIP LOCKED' if self.is_postgres else ''))
            row = db.execute(self._sql(query), args).fetchone()
            if not row:
                return None
            verify_only = row[3] in ('verify_pending', 'write_intent')
            if row[3] == 'processing' and row[4]:
                # A crash while replying must never cause a second write.
                verify_only = True
            db.execute(self._sql("UPDATE review_jobs SET status=%s,attempts=attempts+1,lease_until=%s,updated_at=%s WHERE review_name=%s"),
                       ('verify_pending' if verify_only else 'processing', now + 240, now, row[0]))
            return {'review_name': row[0], 'location_name': row[1], 'attempts': row[2]+1,
                    'verify_only': verify_only, 'reply_text': row[4], 'event_type': row[5]}

    def mark_write_intent(self, review_name, text):
        """Persist the proposed content BEFORE making any external PUT.

        If the process dies after this commit, future claims only verify the write.
        """
        now = time.time()
        with self.connection() as db:
            result = db.execute(self._sql("UPDATE review_jobs SET status='write_intent',reply_text=%s,lease_until=%s,updated_at=%s WHERE review_name=%s AND status='processing'"),
                                (text, now+240, now, review_name))
            if result.rowcount != 1:
                raise RuntimeError('Cannot arm write: processing claim lost')

    def finish(self, review_name, status, reply_text=None, error=None):
        if status not in ('posted', 'existing', 'approval_required'):
            raise ValueError('invalid terminal state')
        with self.connection() as db:
            db.execute(self._sql("UPDATE review_jobs SET status=%s,reply_text=%s,last_error=%s,lease_until=0,updated_at=%s WHERE review_name=%s AND status IN ('processing','write_intent','verify_pending')"),
                       (status, reply_text, (error or '')[:1000], time.time(), review_name))

    def retry(self, review_name, attempts, reason):
        wait = min(3600, 60 * (2 ** min(6, max(0, attempts-1))))
        now = time.time()
        with self.connection() as db:
            # Cannot downgrade a committed write intent into a fresh write attempt.
            db.execute(self._sql("UPDATE review_jobs SET status='retry',next_try=%s,last_error=%s,lease_until=0,updated_at=%s WHERE review_name=%s AND status='processing' AND reply_text IS NULL"),
                       (now+wait, str(reason)[:1000], now, review_name))

    def defer_verify(self, review_name, attempts, reason):
        wait = min(3600, 120 * (2 ** min(5, max(0, attempts-1))))
        now = time.time()
        with self.connection() as db:
            db.execute(self._sql("UPDATE review_jobs SET status='verify_pending',next_try=%s,last_error=%s,lease_until=0,updated_at=%s WHERE review_name=%s AND status IN ('write_intent','verify_pending')"),
                       (now+wait, str(reason)[:1000], now, review_name))

    def job_status(self, review_name):
        with self.connection() as db:
            row = db.execute(self._sql('SELECT status FROM review_jobs WHERE review_name=%s'),
                             (review_name,)).fetchone()
            if row:
                return row[0]
            tomb = db.execute(self._sql('SELECT prior_status FROM review_tombstones WHERE review_hash=%s'),
                              (_digest(review_name),)).fetchone()
            return ('tombstone_' + tomb[0]) if tomb else None

    def job_info(self, review_name):
        """(status, event_type, last_error) for a tracked job; tombstones as status only."""
        with self.connection() as db:
            row = db.execute(self._sql('SELECT status,event_type,last_error FROM review_jobs WHERE review_name=%s'),
                             (review_name,)).fetchone()
            if row:
                return row[0], row[1], row[2] or ''
            tomb = db.execute(self._sql('SELECT prior_status FROM review_tombstones WHERE review_hash=%s'),
                              (_digest(review_name),)).fetchone()
            return (('tombstone_' + tomb[0]), None, '') if tomb else (None, None, '')

    def requalify_for_backfill_2026(self, review_name):
        """Atomically move an approval_required job with NO possible PUT into the 2026 path.

        Only rows that never armed a write qualify: the uncertain-write terminal state
        is excluded, and any write_intent/verify_pending/processing row is untouched.
        Returns True only when exactly one row moved.
        """
        now = time.time()
        with self.connection() as db:
            if not self.is_postgres:
                db.execute('BEGIN IMMEDIATE')
            result = db.execute(self._sql(
                "UPDATE review_jobs SET event_type='BACKFILL_2026',status='queued',attempts=0,"
                "next_try=%s,lease_until=0,reply_text=NULL,last_error=%s,updated_at=%s "
                "WHERE review_name=%s AND status='approval_required' "
                "AND event_type<>'BACKFILL_2026' AND COALESCE(last_error,'')<>%s"),
                (now, 'requalified for 2026 five-star backfill', now, review_name, UNCERTAIN_WRITE_ERROR))
            return result.rowcount == 1

    def release_held_reviews(self, limit=5):
        """Move held reviews back to the queue ONCE under the 'all' scope.

        Only approval_required rows from NEW_REVIEW/BACKFILL that never armed a
        write are eligible; uncertain writes, the 2026 canary path and rows
        already released are never touched. Returns the released review names.
        """
        now = time.time()
        released = []
        with self.connection() as db:
            if not self.is_postgres:
                db.execute('BEGIN IMMEDIATE')
            rows = db.execute(self._sql(
                "SELECT review_name FROM review_jobs WHERE status='approval_required' "
                "AND event_type IN ('NEW_REVIEW','BACKFILL') AND COALESCE(last_error,'')<>%s "
                "ORDER BY created_at LIMIT %s"), (UNCERTAIN_WRITE_ERROR, int(limit))).fetchall()
            for (name,) in rows:
                result = db.execute(self._sql(
                    "UPDATE review_jobs SET event_type='RELEASED',status='queued',attempts=0,next_try=%s,"
                    "lease_until=0,reply_text=NULL,last_error=%s,updated_at=%s WHERE review_name=%s "
                    "AND status='approval_required' AND event_type IN ('NEW_REVIEW','BACKFILL') "
                    "AND COALESCE(last_error,'')<>%s"),
                    (now, 'released under owner scope all', now, name, UNCERTAIN_WRITE_ERROR))
                if result.rowcount == 1:
                    released.append(name)
        return released

    def verified_post_count(self, event_type):
        """Replies confirmed by Google readback (status 'posted' is set only after readback)."""
        with self.connection() as db:
            row = db.execute(self._sql("SELECT COUNT(*) FROM review_jobs WHERE status='posted' AND event_type=%s"),
                             (event_type,)).fetchone()
            return int(row[0] if row else 0)

    def report_by_location(self, event_type):
        with self.connection() as db:
            rows = db.execute(self._sql('SELECT location_name,status,COUNT(*) FROM review_jobs WHERE event_type=%s GROUP BY location_name,status'),
                              (event_type,)).fetchall()
        report = {}
        for location, status, amount in rows:
            report.setdefault(location, {})[status] = int(amount)
        return report

    def recent_replies(self):
        with self.connection() as db:
            rows = db.execute(self._sql("SELECT reply_text FROM review_jobs WHERE reply_text IS NOT NULL AND status='posted' AND updated_at > %s ORDER BY updated_at DESC LIMIT 8"),
                              (time.time()-29*86400,)).fetchall()
            return [row[0] for row in rows]

    def counts(self):
        with self.connection() as db:
            totals = dict(db.execute('SELECT status, COUNT(*) FROM review_jobs GROUP BY status').fetchall())
            expired = db.execute("SELECT amount FROM audit_counters WHERE name='expired_unresolved'").fetchone()
            totals['expired_unresolved_total'] = expired[0] if expired else 0
            return totals

    def prune_old(self):
        """Purge identifiable review content after 29d; keep only hashes for dedupe.

        Unresolved IDs expire too. Keep a counter to require official API backfill
        after permissions return, rather than silently describing them as posted.
        """
        with self.connection() as db:
            if not self.is_postgres:
                db.execute('BEGIN IMMEDIATE')
            rows = db.execute(self._sql('SELECT review_name,status FROM review_jobs WHERE created_at < %s'),
                              (time.time()-29*86400,)).fetchall()
            unresolved = 0
            for resource, status in rows:
                if status not in ('posted', 'existing'):
                    unresolved += 1
                db.execute(self._sql('INSERT INTO review_tombstones(review_hash,prior_status) VALUES (%s,%s) ON CONFLICT(review_hash) DO NOTHING'),
                           (_digest(resource), 'complete' if status in ('posted','existing') else 'expired'))
            db.execute(self._sql('DELETE FROM review_jobs WHERE created_at < %s'), (time.time()-29*86400,))
            if unresolved:
                db.execute(self._sql("INSERT INTO audit_counters(name,amount) VALUES ('expired_unresolved',%s) ON CONFLICT(name) DO UPDATE SET amount=audit_counters.amount + %s"),
                           (unresolved, unresolved))
