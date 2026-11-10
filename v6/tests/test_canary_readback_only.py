"""Regression: authenticated one-review GET-only reconciliation; no Google PUT path."""
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from app import app
from core import ReviewEvent
from storage import Store

LOCATION = 'accounts/118082925604360965903/locations/9619996328379786259'
REVIEW = LOCATION + '/reviews/test-one-canary-readback'
TEXT = 'حياك الله، سعدنا بكلامك الطيب وإشادتك بتعامل فريق الاستقبال وجميع العاملين.'
SECRET = 'local-fixture-only'


class GoogleGetOnly:
    def __init__(self, shown=False):
        self.shown = shown
        self.gets = 0

    def get_review(self, name):
        self.gets += 1
        if name != REVIEW:
            raise AssertionError('wrong review identity')
        return {'name': name,
                'reviewReply': {'comment': TEXT} if self.shown else {}}

    # Intentionally no .reply() method: any Google PUT call fails the test.


class CanaryReadbackOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            'ALLOW_SQLITE_DEV': 'true', 'CRON_SECRET': SECRET,
            'BACKFILL_CANARY_REVIEW': REVIEW,
            'AUTO_REPLY_ENABLED': 'false',
            'BACKFILL_PUBLISH_ENABLED': 'false',
            'OWNER_EXPRESS_CONSENT': 'false',
        })
        self.env.start()
        self.store = Store('sqlite:' + str(Path(self.temp.name) / 'test.db'))
        self.assertTrue(self.store.enqueue(ReviewEvent(REVIEW, LOCATION, 'BACKFILL_2026', 'test')))
        self.assertIsNotNone(self.store.claim(REVIEW))
        self.store.mark_write_intent(REVIEW, TEXT)
        self.store.defer_verify(REVIEW, 1, 'uncertain remote write')
        self.google = GoogleGetOnly()
        self.store_patch = patch('app.get_store', return_value=self.store)
        self.google_patch = patch('app.GoogleClient', return_value=self.google)
        self.store_patch.start()
        self.google_patch.start()
        self.client = app.test_client()

    def tearDown(self):
        self.google_patch.stop()
        self.store_patch.stop()
        self.env.stop()
        self.temp.cleanup()

    def req(self, name=REVIEW, secret=SECRET):
        return self.client.post('/internal/canary-readback-only',
                                json={'review_name': name},
                                headers={'Authorization': 'Bearer ' + secret})

    def test_unauthenticated_refused(self):
        res = self.req(secret='wrong')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(self.google.gets, 0)
        self.assertEqual(self.store.job_status(REVIEW), 'verify_pending')

    def test_other_review_refused_even_with_valid_secret(self):
        res = self.req(name=LOCATION + '/reviews/other')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.google.gets, 0)
        self.assertEqual(self.store.job_status(REVIEW), 'verify_pending')

    def test_not_yet_visible_keeps_verify_pending_no_put(self):
        res = self.req()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'awaiting_google_visibility')
        self.assertEqual(res.get_json()['google_writes'], 0)
        self.assertEqual(self.google.gets, 1)
        self.assertEqual(self.store.job_status(REVIEW), 'verify_pending')

    def test_confirmed_reply_marks_posted_exactly_once(self):
        self.google.shown = True
        first = self.req()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()['status'], 'posted_readback_confirmed')
        self.assertEqual(first.get_json()['google_write_attempted'], False)
        self.assertEqual(first.get_json()['google_writes'], 0)
        self.assertEqual(self.store.job_status(REVIEW), 'posted')
        again = self.req()
        self.assertEqual(again.get_json()['status'], 'not_pending_verification')
        self.assertEqual(self.google.gets, 1)


if __name__ == '__main__':
    unittest.main()
