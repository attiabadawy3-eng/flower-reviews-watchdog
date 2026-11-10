"""2026 five-star backfill: counting, gating, dedupe and single-write safety."""
import datetime as dt
import os
import tempfile
import unittest
from unittest.mock import patch

import backfill_2026
from core import classify_backfill_2026, effective_minimum_stars
from google_client import GoogleAPIError
from processor import process_claimed_job
from storage import Store

NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
LOCS = [f'accounts/9/locations/{i}' for i in range(1, 5)]
BRANCHES = {loc: f'فرع {i}' for i, loc in enumerate(LOCS, 1)}
FLAGS_ON = {'AUTO_REPLY_ENABLED': 'true', 'OWNER_EXPRESS_CONSENT': 'true',
            'BACKFILL_PUBLISH_ENABLED': 'true'}


def review(loc, rid, stars='FIVE', created='2026-03-01T10:00:00Z', reply=None, comment='إقامة مريحة ونظيفة'):
    data = {'name': f'{loc}/reviews/{rid}', 'starRating': stars, 'createTime': created,
            'comment': comment}
    if reply:
        data['reviewReply'] = {'comment': reply}
    return data


class FakeGoogle:
    """Paged listing + per-review GET/PUT with an in-memory 'Google' state."""

    def __init__(self, reviews_by_loc, page_size=2, fail_list=None, put_mode='ok'):
        self.reviews = {r['name']: dict(r) for rows in reviews_by_loc.values() for r in rows}
        self.order = {loc: [r['name'] for r in rows] for loc, rows in reviews_by_loc.items()}
        self.page_size, self.fail_list, self.put_mode = page_size, fail_list, put_mode
        self.puts, self.list_calls = [], []

    def list_reviews(self, location, page_token=None):
        self.list_calls.append((location, page_token))
        if self.fail_list:
            raise GoogleAPIError(self.fail_list, 'blocked')
        names = self.order.get(location, [])
        start = int(page_token or 0)
        chunk = names[start:start + self.page_size]
        out = {'reviews': [dict(self.reviews[n]) for n in chunk]}
        if start + self.page_size < len(names):
            out['nextPageToken'] = str(start + self.page_size)
        return out

    def get_review(self, name):
        return dict(self.reviews[name])

    def reply(self, name, text):
        self.puts.append(name)
        self.reviews[name]['reviewReply'] = {'comment': text}
        if self.put_mode == 'timeout_after_write':
            raise GoogleAPIError(504, 'timeout after commit')
        return {}


class FakeAI:
    n = 0

    def make_reply(self, **kwargs):
        FakeAI.n += 1
        return f'حياك الله، يسعدنا إن إقامتك كانت مريحة ونتشرف بزيارتك مرة ثانية {FakeAI.n}'


class ClassifyTests(unittest.TestCase):
    def test_window_edges_in_riyadh_time(self):
        loc = LOCS[0]
        # 2025-12-31 23:59:59 Riyadh -> outside; 2026-01-01 00:00 Riyadh -> inside
        self.assertEqual(classify_backfill_2026(review(loc, 'a', created='2025-12-31T20:59:59Z'), NOW), 'outside_2026')
        self.assertEqual(classify_backfill_2026(review(loc, 'b', created='2025-12-31T21:00:00Z'), NOW), 'candidate')
        self.assertEqual(classify_backfill_2026(review(loc, 'c', created='2024-06-01T10:00:00Z'), NOW), 'outside_2026')

    def test_future_timestamp_outside(self):
        self.assertEqual(classify_backfill_2026(review(LOCS[0], 'f', created='2026-11-11T10:00:00Z'), NOW), 'outside_2026')

    def test_existing_reply_and_four_star_and_invalid(self):
        loc = LOCS[0]
        self.assertEqual(classify_backfill_2026(review(loc, 'r', reply='شكرًا'), NOW), 'already_replied')
        self.assertEqual(classify_backfill_2026(review(loc, 'f4', stars='FOUR'), NOW), 'below_five')
        self.assertEqual(classify_backfill_2026(review(loc, 'x', created='not-a-date'), NOW), 'invalid')
        self.assertEqual(classify_backfill_2026(review(loc, 'y', stars=None), NOW), 'invalid')

    def test_nanosecond_timestamp_accepted(self):
        self.assertEqual(classify_backfill_2026(review(LOCS[0], 'n', created='2026-05-01T10:00:00.123456789Z'), NOW), 'candidate')

    def test_minimum_stars_never_below_five(self):
        self.assertEqual(effective_minimum_stars('4'), 5)
        self.assertEqual(effective_minimum_stars(1), 5)
        self.assertEqual(effective_minimum_stars(None), 5)
        self.assertEqual(effective_minimum_stars('bad'), 5)


class ScanTests(unittest.TestCase):
    def data(self):
        a, b = LOCS[0], LOCS[1]
        return {
            a: [review(a, 'a1'), review(a, 'a2', reply='تم الرد'), review(a, 'a3', stars='FOUR'),
                review(a, 'a4', created='2025-11-01T10:00:00Z'), review(a, 'a5', created='2026-08-01T10:00:00Z')],
            b: [review(b, 'b1', created='2026-02-01T10:00:00Z')],
            LOCS[2]: [], LOCS[3]: [],
        }

    def test_reads_every_page_and_counts_per_branch(self):
        g = FakeGoogle(self.data(), page_size=2)
        report, candidates = backfill_2026.scan(g, BRANCHES, now=NOW)
        a = report[LOCS[0]]
        self.assertEqual(a['pages'], 3)
        self.assertEqual((a['scanned'], a['candidates'], a['already_replied'], a['below_five'], a['outside_2026']),
                         (5, 2, 1, 1, 1))
        self.assertEqual(report[LOCS[1]]['candidates'], 1)
        self.assertEqual(backfill_2026.totals(report)['candidates'], 3)
        # oldest first
        self.assertEqual([n.rsplit('/', 1)[1] for _, n in candidates], ['b1', 'a1', 'a5'])

    def test_duplicate_across_pages_counted_once(self):
        a = LOCS[0]
        g = FakeGoogle({a: [review(a, 'd1')], LOCS[1]: [], LOCS[2]: [], LOCS[3]: []})
        g.order[a] = [f'{a}/reviews/d1', f'{a}/reviews/d1', f'{a}/reviews/d1']
        report, candidates = backfill_2026.scan(g, BRANCHES, now=NOW)
        self.assertEqual(report[a]['scanned'], 1)
        self.assertEqual(len(candidates), 1)

    def test_foreign_review_name_rejected(self):
        a = LOCS[0]
        g = FakeGoogle({a: [review(LOCS[1], 'z')], LOCS[1]: [], LOCS[2]: [], LOCS[3]: []})
        g.order[a] = [f'{LOCS[1]}/reviews/z']
        report, candidates = backfill_2026.scan(g, BRANCHES, now=NOW)
        self.assertEqual(report[a]['invalid'], 1)
        self.assertEqual(candidates, [])

    def test_google_404_propagates_no_partial_report(self):
        with self.assertRaises(GoogleAPIError):
            backfill_2026.scan(FakeGoogle(self.data(), fail_list=404), BRANCHES, now=NOW)

    def test_page_limit_fails_closed(self):
        with self.assertRaises(backfill_2026.BackfillIncomplete):
            backfill_2026.scan(FakeGoogle(self.data(), page_size=1), BRANCHES, now=NOW, max_pages_per_branch=2)

    def test_requires_four_branches(self):
        with self.assertRaises(ValueError):
            backfill_2026.scan(FakeGoogle({}), {LOCS[0]: 'x'}, now=NOW)

    def test_branch_names_must_be_distinct_non_empty_strings(self):
        for bad in ('', '   ', None, 5):
            mapping = dict(BRANCHES, **{LOCS[3]: bad})
            with self.assertRaises(ValueError, msg=repr(bad)):
                backfill_2026.validate_branches(mapping)
        with self.assertRaises(ValueError):
            backfill_2026.validate_branches(dict(BRANCHES, **{LOCS[3]: BRANCHES[LOCS[0]]}))
        with self.assertRaises(ValueError):
            backfill_2026.validate_branches({'locations/1': 'a', **dict(list(BRANCHES.items())[1:])})


class RunTests(unittest.TestCase):
    """End to end with a real SQLite ledger and the real processor."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ALLOW_SQLITE_DEV': 'true'})
        self.env.start()
        self.store = Store('sqlite:' + self.tmp.name + '/q.sqlite')
        a, b = LOCS[0], LOCS[1]
        self.google = FakeGoogle({
            a: [review(a, 'a1'), review(a, 'a2'), review(a, 'a3', stars='FOUR'),
                review(a, 'a4', reply='موجود')],
            b: [review(b, 'b1', created='2026-01-15T10:00:00Z'), review(b, 'b2', created='2025-06-01T10:00:00Z')],
            LOCS[2]: [], LOCS[3]: [],
        })
        self.canary = f'{LOCS[1]}/reviews/b1'
        self.flags = {'OWNER_EXPRESS_CONSENT': 'true', 'AUTO_REPLY_ENABLED': 'false',
                      'BACKFILL_CANARY_REVIEW': self.canary, 'BACKFILL_PUBLISH_ENABLED': 'false'}

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def process_one(self, name=None):
        """Mirror of app.process_one: general switch from env, 2026 auth per job."""
        job = self.store.claim(name)
        if not job:
            return False
        return process_claimed_job(job=job, store=self.store, google_client=self.google,
                                   ai_generator=FakeAI(), branch_names=BRANCHES,
                                   auto_enabled=self.flags.get('AUTO_REPLY_ENABLED') == 'true',
                                   owner_consent=self.flags.get('OWNER_EXPRESS_CONSENT') == 'true',
                                   minimum_stars=4,
                                   **backfill_2026.job_authorization(self.store, job, self.flags))

    def go(self, mode, canary_review=None):
        return backfill_2026.run(mode, client=self.google, store=self.store, branches=BRANCHES,
                                 process_one=self.process_one, env=self.flags, now=NOW, batch=10,
                                 canary_review=canary_review)

    def add_new_review_event(self, rid='n1'):
        """A fresh NEW_REVIEW (5 stars, now) arriving via Pub/Sub during the canary."""
        from core import ReviewEvent
        loc = LOCS[2]
        name = f'{loc}/reviews/{rid}'
        self.google.reviews[name] = review(loc, rid, created=dt.datetime.now(dt.timezone.utc).isoformat())
        self.assertTrue(self.store.enqueue(ReviewEvent(name, loc, 'NEW_REVIEW', 'pubsub')))
        return name

    def test_dry_run_lists_candidates_for_owner_approval(self):
        self.google.reviews[self.canary]['reviewer'] = {'displayName': 'ضيف'}
        result = self.go('dry_run')
        listed = result['candidate_list']
        self.assertEqual([c['review_name'] for c in listed][0], self.canary)  # oldest first
        self.assertEqual(len(listed), 3)
        first = listed[0]
        self.assertEqual((first['branch'], first['reviewer'], first['ledger_state']), ('فرع 2', 'ضيف', 'new'))
        self.assertTrue(first['comment_preview'])
        # Non-candidates (4 stars, replied, 2025) never listed.
        names = {c['review_name'] for c in listed}
        self.assertNotIn(f'{LOCS[0]}/reviews/a3', names)
        self.assertNotIn(f'{LOCS[0]}/reviews/a4', names)
        self.assertNotIn(f'{LOCS[1]}/reviews/b2', names)
        self.assertEqual(self.google.puts, [])

    def test_dry_run_reports_ledger_and_writes_nothing(self):
        result = self.go('dry_run')
        self.assertEqual(result['totals']['candidates'], 3)
        self.assertEqual(result['google_writes'], 0)
        self.assertEqual(result['ledger_by_branch'][LOCS[0]]['new'], 2)
        self.assertEqual(self.google.puts, [])
        self.assertEqual(self.store.counts().get('queued', 0), 0)

    def test_canary_refused_while_general_auto_reply_on(self):
        self.flags['AUTO_REPLY_ENABLED'] = 'true'
        with self.assertRaises(backfill_2026.BackfillBlocked):
            self.go('canary', self.canary)
        self.assertEqual(self.google.puts, [])

    def test_canary_refused_without_owner_consent(self):
        self.flags['OWNER_EXPRESS_CONSENT'] = 'false'
        with self.assertRaises(backfill_2026.BackfillBlocked):
            self.go('canary', self.canary)
        self.assertEqual(self.google.puts, [])

    def test_canary_must_match_owner_approved_review(self):
        for requested in (None, f'{LOCS[0]}/reviews/a1'):
            with self.assertRaises(backfill_2026.BackfillBlocked):
                self.go('canary', requested)
        self.flags['BACKFILL_CANARY_REVIEW'] = ''
        with self.assertRaises(backfill_2026.BackfillBlocked):
            self.go('canary', self.canary)
        self.assertEqual(self.google.puts, [])

    def test_canary_must_be_a_real_candidate(self):
        four_star = f'{LOCS[0]}/reviews/a3'
        self.flags['BACKFILL_CANARY_REVIEW'] = four_star
        with self.assertRaises(backfill_2026.BackfillBlocked):
            self.go('canary', four_star)
        self.assertEqual(self.google.puts, [])

    def test_canary_posts_only_the_approved_review(self):
        result = self.go('canary', self.canary)
        self.assertEqual(result['canary_status'], 'posted')
        self.assertEqual(self.google.puts, [self.canary])
        self.assertEqual(self.store.verified_post_count('BACKFILL_2026'), 1)

    def test_new_review_during_canary_is_never_posted(self):
        new_name = self.add_new_review_event()
        self.go('canary', self.canary)
        # Drain everything that is due, as the cron would.
        while self.process_one():
            pass
        self.assertEqual(self.google.puts, [self.canary])
        self.assertNotIn(new_name, self.google.puts)
        self.assertEqual(self.store.job_info(new_name)[0], 'approval_required')

    def test_other_2026_jobs_not_posted_by_canary_authorization(self):
        # Another 2026 job already on the backfill path must wait for bulk auth.
        from core import ReviewEvent
        other = f'{LOCS[0]}/reviews/a1'
        self.store.enqueue(ReviewEvent(other, LOCS[0], 'BACKFILL_2026', 'x'))
        self.go('canary', self.canary)
        while self.process_one():
            pass
        self.assertEqual(self.google.puts, [self.canary])
        self.assertEqual(self.store.job_info(other)[0], 'approval_required')

    def test_publish_blocked_without_flag_or_confirmed_canary(self):
        with self.assertRaises(backfill_2026.BackfillBlocked):
            self.go('publish')                      # flag off
        self.flags['BACKFILL_PUBLISH_ENABLED'] = 'true'
        with self.assertRaises(backfill_2026.BackfillBlocked):
            self.go('publish')                      # no confirmed canary yet
        self.assertEqual(self.google.puts, [])
        self.assertEqual(self.store.counts().get('queued', 0), 0)

    def test_canary_then_publish_rest_exactly_once(self):
        self.go('canary', self.canary)
        self.flags['BACKFILL_PUBLISH_ENABLED'] = 'true'
        published = self.go('publish')
        self.assertEqual(sorted(p.rsplit('/', 1)[1] for p in self.google.puts), ['a1', 'a2', 'b1'])
        self.assertEqual(published['confirmed_backfill_replies'], 3)
        self.assertEqual(published['queue_by_branch'][LOCS[0]], {'posted': 2})
        again = self.go('publish')
        self.assertEqual(len(self.google.puts), 3)
        self.assertEqual(again['admitted'], 0)
        self.assertEqual(again['totals']['candidates'], 0)

    def test_publish_does_not_enable_new_review_autopost(self):
        self.go('canary', self.canary)
        self.flags['BACKFILL_PUBLISH_ENABLED'] = 'true'
        new_name = self.add_new_review_event('n2')
        self.go('publish')
        while self.process_one():
            pass
        self.assertNotIn(new_name, self.google.puts)

    def test_reply_added_by_staff_after_listing_is_not_overwritten(self):
        original = self.google.get_review

        def get_with_staff_reply(name):
            data = original(name)
            data['reviewReply'] = {'comment': 'رد الموظف'}
            return data
        self.google.get_review = get_with_staff_reply
        result = self.go('canary', self.canary)
        self.assertEqual(result['canary_status'], 'existing')
        self.assertEqual(self.google.puts, [])

    def test_connection_drop_after_put_never_reposts(self):
        self.google.put_mode = 'timeout_after_write'
        result = self.go('canary', self.canary)
        self.assertEqual(result['canary_status'], 'verify_pending')
        self.assertEqual(len(self.google.puts), 1)
        with self.store.connection() as db:
            db.execute("UPDATE review_jobs SET next_try=0 WHERE review_name=?", (self.canary,))
        self.process_one(self.canary)
        self.assertEqual(len(self.google.puts), 1)
        self.assertEqual(self.store.job_info(self.canary)[0], 'posted')
        self.assertEqual(self.store.verified_post_count('BACKFILL_2026'), 1)


class PreexistingLedgerTests(unittest.TestCase):
    """Candidates already in review_jobs before this change (P1)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ALLOW_SQLITE_DEV': 'true'})
        self.env.start()
        self.store = Store('sqlite:' + self.tmp.name + '/p.sqlite')
        a = LOCS[0]
        self.names = {k: f'{a}/reviews/{k}' for k in ('held', 'uncertain', 'inflight', 'fresh', 'canary')}
        self.google = FakeGoogle({a: [review(a, k) for k in self.names], LOCS[1]: [], LOCS[2]: [], LOCS[3]: []})
        from core import ReviewEvent, UNCERTAIN_WRITE_ERROR
        for key in ('held', 'uncertain', 'inflight'):
            self.store.enqueue(ReviewEvent(self.names[key], a, 'BACKFILL', 'legacy'))
        with self.store.connection() as db:
            db.execute("UPDATE review_jobs SET status='approval_required',reply_text='مسودة',last_error='' WHERE review_name=?",
                       (self.names['held'],))
            db.execute("UPDATE review_jobs SET status='approval_required',reply_text=NULL,last_error=? WHERE review_name=?",
                       (UNCERTAIN_WRITE_ERROR, self.names['uncertain']))
            db.execute("UPDATE review_jobs SET status='verify_pending',reply_text='نص سابق',next_try=9e12 WHERE review_name=?",
                       (self.names['inflight'],))
        self.flags = {'OWNER_EXPRESS_CONSENT': 'true', 'AUTO_REPLY_ENABLED': 'false',
                      'BACKFILL_CANARY_REVIEW': self.names['canary'], 'BACKFILL_PUBLISH_ENABLED': 'true'}

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def process_one(self, name=None):
        job = self.store.claim(name)
        if not job:
            return False
        return process_claimed_job(job=job, store=self.store, google_client=self.google,
                                   ai_generator=FakeAI(), branch_names=BRANCHES,
                                   auto_enabled=False, owner_consent=True, minimum_stars=5,
                                   **backfill_2026.job_authorization(self.store, job, self.flags))

    def go(self, mode, canary_review=None):
        return backfill_2026.run(mode, client=self.google, store=self.store, branches=BRANCHES,
                                 process_one=self.process_one, env=self.flags, now=NOW, batch=10,
                                 canary_review=canary_review)

    def test_dry_run_classifies_ledger_states(self):
        row = self.go('dry_run')['ledger_by_branch'][LOCS[0]]
        self.assertEqual((row['requalifiable'], row['held_uncertain_write'], row['in_flight'], row['new']),
                         (1, 1, 1, 2))

    def test_publish_requalifies_safe_rows_only(self):
        self.go('canary', self.names['canary'])
        result = self.go('publish')
        posted = set(self.google.puts)
        self.assertIn(self.names['held'], posted)          # never written before: requalified
        self.assertIn(self.names['fresh'], posted)
        self.assertNotIn(self.names['uncertain'], posted)  # PUT may have happened: never again
        self.assertNotIn(self.names['inflight'], posted)   # verify-only: never PUT
        self.assertEqual(len(self.google.puts), len(posted))
        self.assertEqual(self.store.job_info(self.names['uncertain'])[0], 'approval_required')
        self.assertEqual(result['ledger_before'][LOCS[0]]['requalifiable'], 1)

    def test_requalify_is_atomic_and_single_use(self):
        self.assertTrue(self.store.requalify_for_backfill_2026(self.names['held']))
        self.assertFalse(self.store.requalify_for_backfill_2026(self.names['held']))
        self.assertFalse(self.store.requalify_for_backfill_2026(self.names['uncertain']))
        self.assertFalse(self.store.requalify_for_backfill_2026(self.names['inflight']))
        status, event_type, _ = self.store.job_info(self.names['held'])
        self.assertEqual((status, event_type), ('queued', 'BACKFILL_2026'))
        job = self.store.claim(self.names['held'])
        self.assertFalse(job['verify_only'])
        self.assertIsNone(job['reply_text'])


class ProcessorPolicyTests(unittest.TestCase):
    """Processor-level guards, independent of the scan pre-filter."""

    class Store:
        def __init__(self):
            self.finished, self.retried, self.deferred, self.intent = [], [], [], []
        def finish(self, *a, **k): self.finished.append((a, k))
        def retry(self, *a): self.retried.append(a)
        def defer_verify(self, *a): self.deferred.append(a)
        def mark_write_intent(self, *a): self.intent.append(a)
        def recent_replies(self): return []

    def run_job(self, data, event_type='BACKFILL_2026', backfill=True, minimum=4, fail=None,
                canary=False, auto=True):
        loc = LOCS[0]
        name = f'{loc}/reviews/p1'
        g = FakeGoogle({loc: [dict(data, name=name)]})
        if fail:
            def boom(_):
                raise GoogleAPIError(fail, 'blocked')
            g.get_review = boom
        s = self.Store()
        process_claimed_job(job={'review_name': name, 'location_name': loc, 'attempts': 1,
                                 'event_type': event_type},
                            store=s, google_client=g, ai_generator=FakeAI(), branch_names=BRANCHES,
                            auto_enabled=auto, owner_consent=True, minimum_stars=minimum,
                            backfill_canary_review=name if canary else None,
                            backfill_bulk_authorized=backfill)
        return s, g

    def test_four_star_new_review_never_autoposted_even_with_min_4(self):
        fresh = dt.datetime.now(dt.timezone.utc).isoformat()
        s, g = self.run_job({'starRating': 'FOUR', 'createTime': fresh, 'comment': 'جيد'},
                            event_type='NEW_REVIEW')
        self.assertEqual(g.puts, [])
        self.assertEqual(s.finished[0][0][1], 'approval_required')

    def test_five_star_new_review_still_autoposted(self):
        fresh = dt.datetime.now(dt.timezone.utc).isoformat()
        s, g = self.run_job({'starRating': 'FIVE', 'createTime': fresh, 'comment': 'ممتاز'},
                            event_type='NEW_REVIEW')
        self.assertEqual(len(g.puts), 1)
        self.assertEqual(s.finished[0][0][1], 'posted')

    def test_backfill_four_star_refused(self):
        s, g = self.run_job({'starRating': 'FOUR', 'createTime': '2026-03-01T10:00:00Z'})
        self.assertEqual(g.puts, [])

    def test_backfill_outside_2026_refused(self):
        s, g = self.run_job({'starRating': 'FIVE', 'createTime': '2025-12-31T20:00:00Z'})
        self.assertEqual(g.puts, [])
        self.assertEqual(s.finished[0][0][1], 'approval_required')

    def test_backfill_needs_its_own_authorization(self):
        s, g = self.run_job({'starRating': 'FIVE', 'createTime': '2026-03-01T10:00:00Z'}, backfill=False)
        self.assertEqual(g.puts, [])

    def test_general_switch_does_not_authorize_backfill(self):
        s, g = self.run_job({'starRating': 'FIVE', 'createTime': '2026-03-01T10:00:00Z'},
                            backfill=False, auto=True)
        self.assertEqual(g.puts, [])

    def test_canary_authorizes_its_own_review_without_general_switch(self):
        s, g = self.run_job({'starRating': 'FIVE', 'createTime': '2026-03-01T10:00:00Z'},
                            backfill=False, canary=True, auto=False)
        self.assertEqual(len(g.puts), 1)

    def test_canary_authorization_is_not_truthy_string(self):
        s, g = self.run_job({'starRating': 'FIVE', 'createTime': '2026-03-01T10:00:00Z'},
                            backfill='true', auto=False)
        self.assertEqual(g.puts, [])

    def test_backfill_high_risk_text_refused(self):
        s, g = self.run_job({'starRating': 'FIVE', 'createTime': '2026-03-01T10:00:00Z',
                             'comment': 'ممتاز لكن صار احتيال في الفاتورة'})
        self.assertEqual(g.puts, [])

    def test_backfill_existing_reply_left_untouched(self):
        s, g = self.run_job({'starRating': 'FIVE', 'createTime': '2026-03-01T10:00:00Z',
                             'reviewReply': {'comment': 'سابق'}})
        self.assertEqual(g.puts, [])
        self.assertEqual(s.finished[0][0][1], 'existing')

    def test_backfill_google_404_retries_without_write(self):
        s, g = self.run_job({'starRating': 'FIVE', 'createTime': '2026-03-01T10:00:00Z'}, fail=404)
        self.assertEqual(g.puts, [])
        self.assertEqual(len(s.retried), 1)

    def test_backfill_eligible_posts_once_with_intent_first(self):
        s, g = self.run_job({'starRating': 'FIVE', 'createTime': '2026-03-01T10:00:00Z'})
        self.assertEqual(len(g.puts), 1)
        self.assertEqual(len(s.intent), 1)
        self.assertEqual(s.finished[0][0][1], 'posted')


class StorageBackfillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ALLOW_SQLITE_DEV': 'true'})
        self.env.start()
        self.path = 'sqlite:' + self.tmp.name + '/s.sqlite'
        self.store = Store(self.path)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_duplicate_enqueue_persists_across_restart(self):
        from core import ReviewEvent
        e = ReviewEvent(f'{LOCS[0]}/reviews/q1', LOCS[0], 'BACKFILL_2026', 'x')
        self.assertTrue(self.store.enqueue(e))
        self.assertFalse(Store(self.path).enqueue(e))
        self.assertEqual(Store(self.path).report_by_location('BACKFILL_2026'), {LOCS[0]: {'queued': 1}})

    def test_completed_tombstone_blocks_backfill_2026(self):
        from core import ReviewEvent
        e = ReviewEvent(f'{LOCS[0]}/reviews/q2', LOCS[0], 'NEW_REVIEW', 'x')
        self.store.enqueue(e)
        self.store.claim()
        self.store.finish(e.review_name, 'existing')
        with self.store.connection() as db:
            db.execute('UPDATE review_jobs SET created_at=0')
        self.store.prune_old()
        self.assertEqual(self.store.job_status(e.review_name), 'tombstone_complete')
        again = ReviewEvent(e.review_name, LOCS[0], 'BACKFILL_2026', 'y')
        self.assertFalse(self.store.enqueue(again))


if __name__ == '__main__':
    unittest.main()
