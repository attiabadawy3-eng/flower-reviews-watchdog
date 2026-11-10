"""Owner scope 'all': reply to every rating; only high-risk text stays manual;
held reviews are released exactly once and never re-sent after an uncertain write."""
import datetime as dt
import os
import tempfile
import unittest
from unittest.mock import patch

from core import ReviewEvent, UNCERTAIN_WRITE_ERROR
from processor import process_claimed_job
from storage import Store
from tests.test_backfill_2026 import BRANCHES, LOCS, FakeAI, FakeGoogle, review


def fresh():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class ScopeAllTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ALLOW_SQLITE_DEV': 'true'})
        self.env.start()
        self.store = Store('sqlite:' + self.tmp.name + '/s.sqlite')
        self.loc = LOCS[3]
        self.google = FakeGoogle({self.loc: [], LOCS[0]: [], LOCS[1]: [], LOCS[2]: []})

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def add(self, rid, stars='ONE', comment='المكيف خربان والغرفة وسخة', created=None, event='NEW_REVIEW'):
        name = f'{self.loc}/reviews/{rid}'
        self.google.reviews[name] = review(self.loc, rid, stars=stars, comment=comment, created=created or fresh())
        self.store.enqueue(ReviewEvent(name, self.loc, event, 'test'))
        return name

    def process(self, name=None, scope='all', auto=True, consent=True, minimum='4'):
        job = self.store.claim(name)
        if not job:
            return False
        return process_claimed_job(job=job, store=self.store, google_client=self.google,
                                   ai_generator=FakeAI(), branch_names=BRANCHES,
                                   auto_enabled=auto, owner_consent=consent,
                                   minimum_stars=minimum, scope=scope)

    def status(self, name):
        return self.store.job_info(name)[0]

    def test_negative_one_star_autoposted_in_scope_all(self):
        name = self.add('n1')
        self.process(name)
        self.assertEqual(self.google.puts, [name])
        self.assertEqual(self.status(name), 'posted')

    def test_high_risk_text_stays_manual_in_scope_all(self):
        name = self.add('h1', comment='صار احتيال في الفاتورة وسرقة')
        self.process(name)
        self.assertEqual(self.google.puts, [])
        self.assertEqual(self.status(name), 'approval_required')

    def test_scope_positive_keeps_negatives_manual(self):
        name = self.add('p1')
        self.process(name, scope='positive')
        self.assertEqual(self.google.puts, [])

    def test_unknown_scope_value_is_positive(self):
        name = self.add('u1')
        self.process(name, scope='everything')
        self.assertEqual(self.google.puts, [])

    def test_general_switch_still_required(self):
        name = self.add('g1')
        self.process(name, auto=False)
        self.assertEqual(self.google.puts, [])

    def test_held_reviews_released_once_and_posted_once(self):
        old = self.add('old', created='2026-10-01T10:00:00Z')   # too old for NEW_REVIEW path
        self.process(old, scope='positive')                       # held under the old policy
        self.assertEqual(self.status(old), 'approval_required')
        released = self.store.release_held_reviews(limit=10)
        self.assertEqual(released, [old])
        self.process(old)                                         # drain under scope all
        self.assertEqual(self.google.puts, [old])
        self.assertEqual(self.status(old), 'posted')
        self.assertEqual(self.store.release_held_reviews(limit=10), [])  # nothing left
        self.assertEqual(len(self.google.puts), 1)

    def test_released_high_risk_never_released_again(self):
        name = self.add('r1', comment='تحرش من الموظف', created='2026-10-01T10:00:00Z')
        self.process(name, scope='positive')
        self.assertEqual(self.store.release_held_reviews(), [name])
        self.process(name)
        self.assertEqual(self.status(name), 'approval_required')
        self.assertEqual(self.store.job_info(name)[1], 'RELEASED')
        self.assertEqual(self.store.release_held_reviews(), [])    # no loop, no repeated AI calls
        self.assertEqual(self.google.puts, [])

    def test_uncertain_write_never_released(self):
        name = self.add('x1')
        with self.store.connection() as db:
            db.execute("UPDATE review_jobs SET status='approval_required',last_error=? WHERE review_name=?",
                       (UNCERTAIN_WRITE_ERROR, name))
        self.assertEqual(self.store.release_held_reviews(), [])
        self.assertEqual(self.google.puts, [])

    def test_in_flight_and_canary_rows_never_released(self):
        a = self.add('w1')
        b = self.add('c1', event='BACKFILL_2026')
        with self.store.connection() as db:
            db.execute("UPDATE review_jobs SET status='verify_pending',reply_text='نص' WHERE review_name=?", (a,))
            db.execute("UPDATE review_jobs SET status='approval_required' WHERE review_name=?", (b,))
        self.assertEqual(self.store.release_held_reviews(), [])

    def test_released_review_already_answered_by_staff_is_left(self):
        name = self.add('s1', created='2026-10-01T10:00:00Z')
        self.process(name, scope='positive')
        self.store.release_held_reviews()
        self.google.reviews[name]['reviewReply'] = {'comment': 'رد الموظف'}
        self.process(name)
        self.assertEqual(self.google.puts, [])
        self.assertEqual(self.status(name), 'existing')

    def test_released_job_never_posts_with_switch_off(self):
        name = self.add('o1', created='2026-10-01T10:00:00Z')
        self.process(name, scope='positive')
        self.store.release_held_reviews()
        self.process(name, auto=False)
        self.assertEqual(self.google.puts, [])


try:
    import flask  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False


@unittest.skipUnless(HAS_FLASK, 'Flask not installed')
class DrainReleaseRouteTests(unittest.TestCase):
    def setUp(self):
        import app as app_module
        self.app_module = app_module
        self.client = app_module.app.test_client()

    def call(self, env):
        from unittest.mock import MagicMock
        store = MagicMock()
        store.release_held_reviews.return_value = ['x']
        store.counts.return_value = {}
        with patch.dict(os.environ, {'CRON_SECRET': 's', **env}), \
             patch.object(self.app_module, 'get_store', return_value=store), \
             patch.object(self.app_module, 'process_one', return_value=False):
            r = self.client.post('/internal/drain', headers={'Authorization': 'Bearer s'})
        return r, store

    def test_release_only_with_scope_all_and_both_switches(self):
        on = {'AUTO_REPLY_SCOPE': 'all', 'AUTO_REPLY_ENABLED': 'true', 'OWNER_EXPRESS_CONSENT': 'true'}
        r, store = self.call(on)
        self.assertEqual(r.get_json()['released'], 1)
        store.release_held_reviews.assert_called_once()
        for off in ({'AUTO_REPLY_SCOPE': 'positive'}, {'AUTO_REPLY_ENABLED': 'false'},
                    {'OWNER_EXPRESS_CONSENT': 'false'}):
            r, store = self.call(dict(on, **off))
            store.release_held_reviews.assert_not_called()
            self.assertEqual(r.get_json()['released'], 0)


if __name__ == '__main__':
    unittest.main()
