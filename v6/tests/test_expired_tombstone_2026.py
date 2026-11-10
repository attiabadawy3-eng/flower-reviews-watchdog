"""Regression: expired unresolved V6 work must never be automatically reposted."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core import ReviewEvent
from storage import Store
from backfill_2026 import _admit, ledger_state, EVENT_TYPE

LOCATION = 'accounts/21/locations/31'
REVIEW = LOCATION + '/reviews/expiredjob'


class TombstoneSafetyTests(unittest.TestCase):
    def test_expired_unresolved_job_is_not_requeued_or_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'ALLOW_SQLITE_DEV': 'true'}):
                store = Store('sqlite:' + str(Path(tmp) / 'ledger.db'))
                self.assertTrue(store.enqueue(ReviewEvent(REVIEW, LOCATION, 'NEW_REVIEW', 'initial')))
                self.assertIsNotNone(store.claim(REVIEW))
                store.finish(REVIEW, 'approval_required', reply_text='unpublished draft')
                with store.connection() as db:
                    db.execute('UPDATE review_jobs SET created_at=? WHERE review_name=?',
                               (time.time() - 31 * 86400, REVIEW))
                store.prune_old()
                self.assertEqual(store.job_info(REVIEW)[0], 'tombstone_expired')
                self.assertEqual(ledger_state(store, REVIEW), 'tombstone_expired')
                self.assertFalse(store.enqueue(ReviewEvent(REVIEW, LOCATION, EVENT_TYPE, 'retry')))
                self.assertFalse(_admit(store, LOCATION, REVIEW, 'tombstone_expired', 'retry'))
                self.assertEqual(store.job_info(REVIEW)[0], 'tombstone_expired')

    def test_complete_tombstone_stays_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'ALLOW_SQLITE_DEV': 'true'}):
                store = Store('sqlite:' + str(Path(tmp) / 'ledger.db'))
                self.assertTrue(store.enqueue(ReviewEvent(REVIEW, LOCATION, 'NEW_REVIEW', 'initial')))
                self.assertIsNotNone(store.claim(REVIEW))
                store.finish(REVIEW, 'posted', reply_text='confirmed')
                with store.connection() as db:
                    db.execute('UPDATE review_jobs SET created_at=? WHERE review_name=?',
                               (time.time() - 31 * 86400, REVIEW))
                store.prune_old()
                self.assertEqual(store.job_info(REVIEW)[0], 'tombstone_complete')
                self.assertFalse(store.enqueue(ReviewEvent(REVIEW, LOCATION, EVENT_TYPE, 'retry')))


if __name__ == '__main__':
    unittest.main()
