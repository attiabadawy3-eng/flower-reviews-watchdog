import os
import tempfile
import unittest
from unittest.mock import patch
from core import ReviewEvent
from storage import Store


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = 'sqlite:' + self.tmp.name + '/review.sqlite'
        self.env = patch.dict(os.environ, {'ALLOW_SQLITE_DEV': 'true'})
        self.env.start()
        self.store = Store(self.path)
        self.event = ReviewEvent('accounts/12/locations/34/reviews/r1', 'accounts/12/locations/34', 'NEW_REVIEW', 'id1')

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_persistent_deduplication(self):
        self.assertTrue(self.store.enqueue(self.event))
        self.assertFalse(self.store.enqueue(self.event))
        self.assertEqual(Store(self.path).counts()['queued'], 1)

    def test_claim_and_done_only_once(self):
        self.store.enqueue(self.event)
        c = self.store.claim()
        self.assertEqual(c['review_name'], self.event.review_name)
        self.assertEqual(c['attempts'], 1)
        self.assertIsNone(self.store.claim())
        self.store.finish(self.event.review_name, 'existing')
        self.assertIsNone(self.store.claim())
        self.assertEqual(self.store.counts()['existing'], 1)

    def test_retry_is_delayed(self):
        self.store.enqueue(self.event)
        claim = self.store.claim()
        self.store.retry(self.event.review_name, claim['attempts'], 'HTTP 404')
        self.assertIsNone(self.store.claim())
        self.assertEqual(self.store.counts()['retry'], 1)

    def test_approval_queue_is_not_auto_retried(self):
        self.store.enqueue(self.event)
        self.store.claim()
        self.store.finish(self.event.review_name, 'approval_required', reply_text='شكراً لك على مشاركة تجربتك مع فلور، ويسعدنا استقبالك مجدداً.')
        self.assertIsNone(self.store.claim())
        self.assertEqual(self.store.counts()['approval_required'], 1)

    def test_production_requires_persistent_db(self):
        with patch.dict(os.environ, {'ALLOW_SQLITE_DEV': 'false'}):
            with self.assertRaises(RuntimeError):
                Store(self.path)


    def test_write_intent_survives_crash_and_reclaims_verify_only(self):
        self.store.enqueue(self.event)
        claim=self.store.claim()
        self.store.mark_write_intent(self.event.review_name, 'جهزنا رد واحد للتقييم لحماية منع التكرار.')
        with self.store.connection() as db:
            db.execute("UPDATE review_jobs SET lease_until=0 WHERE review_name=?",(self.event.review_name,))
        second=Store(self.path).claim()
        self.assertTrue(second['verify_only'])
        self.assertEqual(second['reply_text'],'جهزنا رد واحد للتقييم لحماية منع التكرار.')
        self.assertEqual(second['attempts'],2)
        self.store.defer_verify(self.event.review_name,second['attempts'],'awaiting readback')
        self.assertIsNone(self.store.claim())
        self.assertEqual(self.store.counts()['verify_pending'],1)

    def test_29_day_expiry_leaves_only_hash_and_dedupes_posted(self):
        self.store.enqueue(self.event)
        self.store.claim()
        self.store.finish(self.event.review_name,'posted',reply_text='رد سعودي سابق')
        with self.store.connection() as db:
            db.execute("UPDATE review_jobs SET created_at=0 WHERE review_name=?",(self.event.review_name,))
        self.store.prune_old()
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM review_jobs').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT LENGTH(review_hash) FROM review_tombstones').fetchone()[0],64)
        self.assertFalse(self.store.enqueue(self.event))

    def test_expired_unresolved_can_reenter_only_as_explicit_backfill(self):
        self.store.enqueue(self.event)
        with self.store.connection() as db:
            db.execute("UPDATE review_jobs SET created_at=0 WHERE review_name=?",(self.event.review_name,))
        self.store.prune_old()
        self.assertFalse(self.store.enqueue(self.event))
        requeue = ReviewEvent(self.event.review_name,self.event.location_name,'BACKFILL','manual')
        self.assertTrue(self.store.enqueue(requeue))
        recovered = self.store.claim()
        self.assertEqual(recovered['event_type'],'BACKFILL')

    def test_completed_review_never_requeued_even_via_backfill(self):
        self.store.enqueue(self.event);self.store.claim()
        self.store.finish(self.event.review_name,'posted')
        with self.store.connection() as db:
            db.execute("UPDATE review_jobs SET created_at=0 WHERE review_name=?",(self.event.review_name,))
        self.store.prune_old()
        requeue=ReviewEvent(self.event.review_name,self.event.location_name,'BACKFILL','manual')
        self.assertFalse(self.store.enqueue(requeue))

    def test_expired_unresolved_is_counted_not_misreported_posted(self):
        self.store.enqueue(self.event)
        with self.store.connection() as db:
            db.execute("UPDATE review_jobs SET created_at=0 WHERE review_name=?",(self.event.review_name,))
        self.store.prune_old()
        self.assertEqual(self.store.counts()['expired_unresolved_total'],1)
        self.assertFalse(self.store.enqueue(self.event))

if __name__ == '__main__':
    unittest.main()
