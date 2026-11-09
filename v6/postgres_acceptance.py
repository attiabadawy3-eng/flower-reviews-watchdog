"""One-time Neon PostgreSQL acceptance test in an isolated, disposable schema.

Usage (on the authorized operator workstation):
    FLOWER_NEON_TEST_DATABASE_URL=<direct Neon URL> python v6/postgres_acceptance.py

Never prints connection credentials or URL. Never contacts Google or posts replies.
Creates a random test-only schema and drops it in a finally block.
"""
import json
import os
import secrets
import sys
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from core import ReviewEvent
from storage import Store


def validate_direct_neon_url(dsn):
    """Require actual Neon, TLS, and a direct endpoint for test schema setup."""
    if not dsn:
        raise ValueError('FLOWER_NEON_TEST_DATABASE_URL is required')
    parts = conninfo_to_dict(dsn)
    host = str(parts.get('host') or '').lower()
    sslmode = str(parts.get('sslmode') or '').lower()
    if not host.endswith('.neon.tech') or host.startswith('.') or '-pooler.' in host:
        raise ValueError('Neon direct PostgreSQL endpoint required for isolated schema test')
    if sslmode not in ('require', 'verify-ca', 'verify-full'):
        raise ValueError('TLS sslmode=require or stronger is required')
    if not (parts.get('user') and parts.get('dbname')):
        raise ValueError('database and role must be specified')
    return True


def run_postgres_acceptance(dsn):
    validate_direct_neon_url(dsn)
    schema = 'flower_reviews_v6_acceptance_' + secrets.token_hex(6)
    results = []
    schema_created = False
    try:
        with psycopg.connect(dsn, connect_timeout=20) as admin:
            admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        schema_created = True
        isolated_dsn = dsn + ('&' if '?' in dsn else '?') + 'options=' + quote('-csearch_path=' + schema)
        store = Store(isolated_dsn)
        assert store.is_postgres, 'Postgres adapter was not selected'
        results.append('isolated_schema_initialized')

        first = 'accounts/99901/locations/99902/reviews/test_a_' + secrets.token_hex(6)
        loc = 'accounts/99901/locations/99902'
        event = ReviewEvent(first, loc, 'NEW_REVIEW', 'neon-integration-test')
        assert store.enqueue(event)
        assert not store.enqueue(event)
        job = store.claim(first)
        assert job and not job['verify_only'] and job['attempts'] == 1
        store.mark_write_intent(first, 'Approved test text - not sent to Google')
        results.append('idempotent_queue_and_write_intent')

        # Force expiry of the test-only claim: restarting must only verify,
        # never prepare a second external write.
        with store.connection() as db:
            db.execute('UPDATE review_jobs SET lease_until=0 WHERE review_name=%s', (first,))
        reopened = Store(isolated_dsn)
        recovered = reopened.claim(first)
        assert recovered and recovered['verify_only']
        assert recovered['reply_text'] == 'Approved test text - not sent to Google'
        reopened.finish(first, 'posted', reply_text=recovered['reply_text'])
        assert reopened.counts().get('posted') == 1
        assert not reopened.enqueue(event)
        results.append('restart_recovers_verify_only_no_repost')

        second = 'accounts/99901/locations/99902/reviews/test_b_' + secrets.token_hex(6)
        assert store.enqueue(ReviewEvent(second, loc, 'NEW_REVIEW', 'concurrency-test'))
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _: Store(isolated_dsn).claim(second), range(2)))
        winners = [item for item in claims if item is not None]
        assert len(winners) == 1
        store.finish(second, 'existing')
        results.append('postgres_concurrent_claim_single_winner')

        with store.connection() as db:
            db.execute('UPDATE review_jobs SET created_at=0 WHERE review_name=%s', (first,))
        store.prune_old()
        assert not store.enqueue(event)
        assert reopened.counts().get('existing') == 1
        results.append('tombstone_prevents_requeue')

        return {'status': 'passed', 'checks': results,
                'google_requests': 0, 'google_write_requests': 0,
                'test_schema_deleted_after_run': True}
    finally:
        if schema_created:
            with psycopg.connect(dsn, connect_timeout=20) as admin:
                admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def main():
    try:
        result = run_postgres_acceptance(os.environ.get('FLOWER_NEON_TEST_DATABASE_URL'))
        print(json.dumps(result))
    except Exception as exc:
        # Never dump exception details: libpq errors can contain connection data.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__,
                          'google_requests': 0, 'google_write_requests': 0}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
