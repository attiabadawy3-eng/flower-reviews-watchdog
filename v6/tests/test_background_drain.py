"""In-process drain: starts once, only with real storage, never doubles work."""
import os
import threading
import unittest
from unittest.mock import MagicMock, patch

try:
    import flask  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False


@unittest.skipUnless(HAS_FLASK, 'Flask not installed')
class BackgroundDrainTests(unittest.TestCase):
    def setUp(self):
        import app as app_module
        self.app = app_module
        self.saved = dict(app_module._worker_state)
        app_module._worker_state.update({'started': False, 'last_run': None, 'last_error': None, 'passes': 0})

    def tearDown(self):
        self.app._worker_state.update(self.saved)

    def test_disabled_without_database(self):
        with patch.dict(os.environ, {'DATABASE_URL': ''}), patch.object(threading, 'Thread') as t:
            self.assertFalse(self.app.ensure_background_drain())
            t.assert_not_called()

    def test_can_be_switched_off(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://x', 'BACKGROUND_DRAIN_ENABLED': 'false'}), \
             patch.object(threading, 'Thread') as t:
            self.assertFalse(self.app.ensure_background_drain())
            t.assert_not_called()

    def test_starts_exactly_once(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://x', 'BACKGROUND_DRAIN_ENABLED': 'true'}), \
             patch.object(self.app.threading, 'Thread') as t:
            self.assertTrue(self.app.ensure_background_drain())
            self.assertFalse(self.app.ensure_background_drain())
            self.assertEqual(t.call_count, 1)
            self.assertTrue(t.call_args.kwargs['daemon'])

    def test_interval_has_floor_and_default(self):
        with patch.dict(os.environ, {'BACKGROUND_DRAIN_SECONDS': '5'}):
            self.assertEqual(self.app.background_drain_interval(), 30)
        with patch.dict(os.environ, {'BACKGROUND_DRAIN_SECONDS': 'bad'}):
            self.assertEqual(self.app.background_drain_interval(), 120)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('BACKGROUND_DRAIN_SECONDS', None)
            self.assertEqual(self.app.background_drain_interval(), 120)

    def test_pass_uses_same_drain_and_records_state(self):
        store = MagicMock()
        store.release_held_reviews.return_value = []
        store.counts.return_value = {'posted': 5}
        with patch.object(self.app, 'get_store', return_value=store), \
             patch.object(self.app, 'process_one', side_effect=[True, False]):
            result = self.app.background_drain_pass()
        self.assertEqual(result['processed'], 1)
        self.assertEqual(self.app._worker_state['passes'], 1)
        self.assertIsNotNone(self.app._worker_state['last_run'])

    def test_drain_passes_are_serialized(self):
        """HTTP drain and the thread share one lock: never two passes at once."""
        running, overlap = [], []

        def fake_unlocked():
            if running:
                overlap.append(True)
            running.append(1)
            threading.Event().wait(0.05)
            running.pop()
            return {'processed': 0, 'released': 0, 'jobs': {}}
        with patch.object(self.app, '_run_drain_unlocked', side_effect=fake_unlocked):
            ts = [threading.Thread(target=self.app.run_drain) for _ in range(4)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        self.assertEqual(overlap, [])

    def test_http_drain_still_authenticated_and_same_shape(self):
        client = self.app.app.test_client()
        with patch.dict(os.environ, {'CRON_SECRET': 's', 'DATABASE_URL': ''}):
            self.assertEqual(client.post('/internal/drain').status_code, 401)
            with patch.object(self.app, 'run_drain', return_value={'processed': 0, 'released': 0, 'jobs': {}}):
                r = client.post('/internal/drain', headers={'Authorization': 'Bearer s'})
        self.assertEqual(r.get_json(), {'processed': 0, 'released': 0, 'jobs': {}})


if __name__ == '__main__':
    unittest.main()
