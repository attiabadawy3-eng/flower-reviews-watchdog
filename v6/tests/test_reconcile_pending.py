"""GET-only reconciliation tests with durable SQLite; zero Google write methods."""
import os
import tempfile
import unittest
from unittest.mock import patch

from core import ReviewEvent
from reconcile_pending import reconcile_pending
from storage import Store

REVIEW = 'accounts/12/locations/34/reviews/only-one'
LOCATION = 'accounts/12/locations/34'
APPROVED = 'حياك الله، شاكرين لك ثقتك في فلور ونتشرف فيك دائمًا.'
TRANSLATED = APPROVED + '\n\n(Translated by Google) Welcome! Thanks for visiting.'


class ReadOnlyGoogle:
    def __init__(self, comment, state=None):
        self.comment = comment
        self.state = state
        self.calls = 0

    def get_review(self, name):
        self.calls += 1
        r = {'name': name}
        if self.comment is not None:
            r['reviewReply'] = {'comment': self.comment}
            if self.state:
                r['reviewReply']['reviewReplyState'] = self.state
        return r
    # No reply/PUT method is deliberately provided.


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ALLOW_SQLITE_DEV': 'true'})
        self.env.start()
        self.ledger = Store('sqlite:' + self.temp.name + '/pilot.sqlite')
        event = ReviewEvent(REVIEW, LOCATION, 'NEW_REVIEW', 'pilot-one')
        self.ledger.enqueue(event)
        self.ledger.claim(REVIEW)
        self.ledger.mark_write_intent(REVIEW, APPROVED)
        self.ledger.defer_verify(REVIEW, 1, 'waiting on Google readback')

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def get_status(self):
        with self.ledger.connection() as db:
            return db.execute('SELECT status FROM review_jobs WHERE review_name=?', (REVIEW,)).fetchone()[0]

    def test_translated_reply_marks_posted_without_google_put(self):
        google = ReadOnlyGoogle(TRANSLATED, 'APPROVED')
        result = reconcile_pending(REVIEW, store=self.ledger, google=google)
        self.assertEqual(result['status'], 'posted_readback_confirmed')
        self.assertFalse(result['google_write_attempted'])
        self.assertEqual(google.calls, 1)
        self.assertEqual(self.get_status(), 'posted')

    def test_repeat_does_not_write_or_relabel(self):
        google = ReadOnlyGoogle(TRANSLATED)
        self.assertEqual(reconcile_pending(REVIEW, store=self.ledger, google=google)['status'],
                         'posted_readback_confirmed')
        self.assertEqual(reconcile_pending(REVIEW, store=self.ledger, google=google)['status'],
                         'not_pending_verification')
        self.assertEqual(google.calls, 1)

    def test_mismatch_is_left_pending_not_called_another_owner(self):
        google = ReadOnlyGoogle(APPROVED + ' تعديل آخر\n\n(Translated by Google) Welcome!')
        result = reconcile_pending(REVIEW, store=self.ledger, google=google)
        self.assertEqual(result['status'], 'manual_review_text_mismatch')
        self.assertEqual(self.get_status(), 'verify_pending')

    def test_missing_reply_is_left_pending(self):
        result = reconcile_pending(REVIEW, store=self.ledger, google=ReadOnlyGoogle(None))
        self.assertEqual(result['status'], 'awaiting_google_visibility')
        self.assertEqual(self.get_status(), 'verify_pending')

    def test_pending_moderation_stays_pending(self):
        result = reconcile_pending(REVIEW, store=self.ledger, google=ReadOnlyGoogle(TRANSLATED, 'PENDING'))
        self.assertEqual(result['status'], 'google_moderation_pending')
        self.assertEqual(self.get_status(), 'verify_pending')

    def test_rejected_moderation_stays_pending_for_manual_resolution(self):
        result = reconcile_pending(REVIEW, store=self.ledger, google=ReadOnlyGoogle(TRANSLATED, 'REJECTED'))
        self.assertEqual(result['status'], 'google_reply_rejected')
        self.assertEqual(self.get_status(), 'verify_pending')

    def test_missing_ledger_no_google_call(self):
        g = ReadOnlyGoogle(TRANSLATED)
        result = reconcile_pending('accounts/12/locations/34/reviews/unknown', store=self.ledger, google=g)
        self.assertEqual(result['status'], 'ledger_entry_not_found')
        self.assertEqual(g.calls, 0)


if __name__ == '__main__':
    unittest.main()
