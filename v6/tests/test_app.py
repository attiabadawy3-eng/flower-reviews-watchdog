"""Flask route tests. CI installs Flask; the offline analysis environment may not."""
import base64
import json
import os
import unittest
from unittest.mock import patch

try:
    import flask  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False


@unittest.skipUnless(HAS_FLASK, 'Flask not installed in this offline environment')
class AppEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls.app_module = app_module

    def setUp(self):
        self.client = self.app_module.app.test_client()

    def test_pubsub_without_google_oidc_unauthorized(self):
        with patch.object(self.app_module, 'authenticate_pubsub', return_value=False):
            response = self.client.post('/pubsub/reviews', json={'message': {}})
        self.assertEqual(response.status_code, 401)

    def test_pubsub_bad_envelope_rejected(self):
        with patch.object(self.app_module, 'authenticate_pubsub', return_value=True):
            response = self.client.post('/pubsub/reviews', json={'message': {'data': '$notbase64'}})
        self.assertEqual(response.status_code, 400)

    def test_non_review_event_is_acknowledged(self):
        d = base64.b64encode(json.dumps({'type':'GOOGLE_UPDATE'}).encode()).decode()
        with patch.object(self.app_module, 'authenticate_pubsub', return_value=True):
            response = self.client.post('/pubsub/reviews', json={'message': {'messageId':'x','data':d}})
        self.assertEqual(response.status_code, 204)

    def test_stored_message_acknowledged_when_processing_crashes(self):
        from unittest.mock import MagicMock
        payload = {'type':'NEW_REVIEW','review':'accounts/12/locations/34/reviews/abc',
                   'location':'accounts/12/locations/34'}
        d = base64.b64encode(json.dumps(payload).encode()).decode()
        store = MagicMock()
        store.enqueue.return_value = True
        with patch.object(self.app_module, 'authenticate_pubsub', return_value=True), \
             patch.object(self.app_module, 'get_store', return_value=store), \
             patch.object(self.app_module, 'process_one', side_effect=RuntimeError('offline')):
            response = self.client.post('/pubsub/reviews', json={'message': {'messageId':'x','data':d}})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(store.enqueue.call_count,1)

    def test_drain_requires_secret(self):
        with patch.dict(os.environ, {'CRON_SECRET':'test-secret'}):
            response = self.client.post('/internal/drain')
        self.assertEqual(response.status_code, 401)

    def test_liveness_does_not_claim_api_health(self):
        response=self.client.get('/live')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json()['google_reviews_api'],'not_checked')

    def test_storage_health_reports_ready_when_db_works(self):
        from unittest.mock import MagicMock
        store = MagicMock()
        store.counts.return_value = {'posted': 1}
        with patch.object(self.app_module, 'get_store', return_value=store), \
             patch.dict(os.environ, {'AUTO_REPLY_ENABLED': 'false'}):
            response = self.client.get('/health/storage')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['database'], 'postgres')
        self.assertEqual(response.get_json()['jobs']['posted'], 1)
        self.assertFalse(response.get_json()['auto_reply_enabled'])

    def test_storage_health_fails_closed_on_db_error(self):
        with patch.object(self.app_module, 'get_store', side_effect=RuntimeError('offline')):
            response = self.client.get('/health/storage')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()['status'], 'storage_unavailable')

    def test_health_does_not_claim_reviews_api_success(self):
        from unittest.mock import MagicMock
        store=MagicMock()
        store.counts.return_value={'queued':1}
        with patch.object(self.app_module, 'get_store', return_value=store), \
             patch.dict(os.environ, {'BRANCH_NAMES_JSON':'{}'}, clear=False):
            response=self.client.get('/health')
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.get_json()['google_reviews_api'],'not_checked')

if __name__ == '__main__': unittest.main()
