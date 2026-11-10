"""The manual pilot must never post without exact owner consent and durable dedupe."""
import datetime as dt
import hashlib
import os
import unittest
from unittest import mock

from manual_first_reply import perform_pilot

REVIEW = 'accounts/12/locations/34/reviews/approved001'
LOCATION = 'accounts/12/locations/34'
TEXT = 'حياك الله، شاكرين لك ثقتك في فلور ونتشرف فيك دائمًا.'


class FakeGoogle:
    def __init__(self):
        self.writes = []
        self.existing = None
        self.reads = 0

    def get_review(self, name):
        self.reads += 1
        result = {
            'name': name, 'starRating': 'FIVE', 'comment': '',
            'createTime': dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        if self.existing:
            result['reviewReply'] = {'comment': self.existing}
        return result

    def reply(self, name, text):
        self.writes.append((name, text))
        self.existing = text
        return {'comment': text}


class FakeStore:
    def __init__(self):
        self.enqueued = False
        self.intent = []
        self.finished = []

    def enqueue(self, event):
        if self.enqueued:
            return False
        self.enqueued = True
        return True

    def claim(self, name):
        return {'review_name': name, 'location_name': LOCATION, 'attempts': 1,
                'event_type': 'NEW_REVIEW'}

    def recent_replies(self):
        return []

    def mark_write_intent(self, *a):
        self.intent.append(a)

    def finish(self, *a, **kw):
        self.finished.append((a, kw))


def approved_env():
    branches = {LOCATION: 'فلور 1 العنود'}
    for i in (35, 36, 37):
        branches[f'accounts/12/locations/{i}'] = f'فلور {i}'
    return {
        'OWNER_EXPRESS_CONSENT': 'true',
        'OWNER_APPROVED_REVIEW_NAME': REVIEW,
        'OWNER_APPROVED_REPLY_SHA256': hashlib.sha256(TEXT.encode()).hexdigest(),
        'BRANCH_NAMES_JSON': __import__('json').dumps(branches),
    }


class ManualPilotTests(unittest.TestCase):
    def test_default_is_read_only(self):
        g = FakeGoogle()
        self.assertEqual(perform_pilot(REVIEW, TEXT, google=g)['status'], 'dry_run_no_write')
        self.assertEqual(g.writes, [])

    def test_no_approval_never_writes(self):
        g = FakeGoogle()
        with mock.patch.dict(os.environ, {'OWNER_EXPRESS_CONSENT': 'false'}):
            with self.assertRaises(PermissionError):
                perform_pilot(REVIEW, TEXT, publish=True, google=g)
        self.assertEqual(g.writes, [])

    def test_wrong_text_hash_never_writes(self):
        g = FakeGoogle()
        config = approved_env()
        config['OWNER_APPROVED_REPLY_SHA256'] = '0' * 64
        with mock.patch.dict(os.environ, config):
            with self.assertRaises(PermissionError):
                perform_pilot(REVIEW, TEXT, publish=True, google=g)
        self.assertEqual(g.writes, [])

    def test_existing_reply_is_not_replaced(self):
        g = FakeGoogle()
        g.existing = 'رد الموظف السابق'
        with mock.patch.dict(os.environ, approved_env()):
            result = perform_pilot(REVIEW, TEXT, publish=True, google=g)
        self.assertEqual(result['status'], 'already_replied')
        self.assertEqual(g.writes, [])

    def test_exact_approved_one_write_and_readback(self):
        g = FakeGoogle()
        s = FakeStore()
        with mock.patch.dict(os.environ, approved_env()):
            result = perform_pilot(REVIEW, TEXT, publish=True, google=g, store=s)
            repeat = perform_pilot(REVIEW, TEXT, publish=True, google=g, store=s)
        self.assertEqual(result['status'], 'posted_readback_confirmed')
        self.assertEqual(repeat['status'], 'already_replied')
        self.assertEqual(g.writes, [(REVIEW, TEXT)])
        self.assertEqual(len(s.intent), 1)
        self.assertEqual(s.finished[0][0][1], 'posted')

    def test_durable_ledger_prevents_repost_after_reply_disappears(self):
        g = FakeGoogle()
        s = FakeStore()
        with mock.patch.dict(os.environ, approved_env()):
            perform_pilot(REVIEW, TEXT, publish=True, google=g, store=s)
            g.existing = None
            again = perform_pilot(REVIEW, TEXT, publish=True, google=g, store=s)
        self.assertEqual(again['status'], 'already_in_durable_ledger')
        self.assertEqual(len(g.writes), 1)



    def test_single_pilot_readback_accepts_google_translation(self):
        class TranslatedGoogle(FakeGoogle):
            def get_review(self, name):
                data = super().get_review(name)
                if self.existing:
                    data['reviewReply']['comment'] += (
                        '\n\n(Translated by Google) Welcome, thank you for visiting.'
                    )
                return data
        g = TranslatedGoogle()
        s = FakeStore()
        with mock.patch.dict(os.environ, approved_env()):
            result = perform_pilot(REVIEW, TEXT, publish=True, google=g, store=s)
            repeat = perform_pilot(REVIEW, TEXT, publish=True, google=g, store=s)
        self.assertEqual(result['status'], 'posted_readback_confirmed')
        self.assertEqual(repeat['status'], 'already_replied')
        self.assertEqual(g.writes, [(REVIEW, TEXT)])
        self.assertEqual(s.finished[0][0][1], 'posted')

if __name__ == '__main__':
    unittest.main()
