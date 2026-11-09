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

    def test_google_probe_requires_internal_secret(self):
        with patch.dict(os.environ, {'CRON_SECRET': 'test-secret'}):
            response = self.client.post('/internal/google-probe')
        self.assertEqual(response.status_code, 401)

    def test_google_probe_reads_all_four_without_google_writes(self):
        from unittest.mock import MagicMock
        g = MagicMock()
        g.list_reviews.return_value = {'reviews': []}
        mapping = {'accounts/12/locations/' + str(i): 'فلور ' + str(i)
                   for i in range(1, 5)}
        with patch.dict(os.environ, {'CRON_SECRET': 'test-secret',
                                       'BRANCH_NAMES_JSON': json.dumps(mapping),
                                       'AUTO_REPLY_ENABLED': 'false'}), \
             patch.object(self.app_module, 'GoogleClient', return_value=g):
            response = self.client.post('/internal/google-probe',
                                        headers={'Authorization': 'Bearer test-secret'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['branches_checked'], 4)
        self.assertEqual(response.get_json()['google_writes'], 0)
        self.assertFalse(response.get_json()['auto_reply_enabled'])
        self.assertEqual(g.list_reviews.call_count, 4)
        g.reply.assert_not_called()
        g.get_review.assert_not_called()

    def test_google_probe_error_fails_closed(self):
        from unittest.mock import MagicMock
        from google_client import GoogleAPIError
        g = MagicMock()
        g.list_reviews.side_effect = GoogleAPIError(429, 'test quota')
        mapping = {'accounts/12/locations/' + str(i): 'فلور ' + str(i)
                   for i in range(1, 5)}
        with patch.dict(os.environ, {'CRON_SECRET': 'test-secret',
                                       'BRANCH_NAMES_JSON': json.dumps(mapping)}), \
             patch.object(self.app_module, 'GoogleClient', return_value=g):
            response = self.client.post('/internal/google-probe',
                                        headers={'Authorization': 'Bearer test-secret'})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()['provider_http'], 429)
        self.assertEqual(response.get_json()['google_writes'], 0)
        g.reply.assert_not_called()

    def test_ai_preview_requires_internal_secret(self):
        with patch.dict(os.environ, {'CRON_SECRET': 'test-secret'}):
            response = self.client.post('/internal/ai-preview',
                                        json={'branch': 'فلور 1', 'stars': 5})
        self.assertEqual(response.status_code, 401)

    def test_ai_preview_generates_draft_without_google_write(self):
        from unittest.mock import MagicMock
        gen = MagicMock()
        gen.make_reply.return_value = 'حياك الله، شاكرين لك ثقتك في فلور ونتشرف فيك دائمًا.'
        mapping = {'accounts/12/locations/' + str(i): 'فلور ' + str(i)
                   for i in range(1, 5)}
        with patch.dict(os.environ, {'CRON_SECRET': 'test-secret',
                                       'BRANCH_NAMES_JSON': json.dumps(mapping)}), \
             patch.object(self.app_module, 'SaudiReplyGenerator', return_value=gen), \
             patch.object(self.app_module, 'GoogleClient') as g:
            response = self.client.post('/internal/ai-preview',
                headers={'Authorization': 'Bearer test-secret'},
                json={'branch': 'فلور 1', 'stars': 5, 'comment': 'نظيف ومرتب'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['status'], 'draft_only')
        self.assertEqual(response.get_json()['google_writes'], 0)
        gen.make_reply.assert_called_once()
        g.assert_not_called()

    def test_ai_preview_wrong_branch_rejected_without_model_call(self):
        from unittest.mock import MagicMock
        gen = MagicMock()
        mapping = {'accounts/12/locations/' + str(i): 'فلور ' + str(i)
                   for i in range(1, 5)}
        with patch.dict(os.environ, {'CRON_SECRET': 'test-secret',
                                       'BRANCH_NAMES_JSON': json.dumps(mapping)}), \
             patch.object(self.app_module, 'SaudiReplyGenerator', return_value=gen):
            response = self.client.post('/internal/ai-preview',
                headers={'Authorization': 'Bearer test-secret'},
                json={'branch': 'غير معروف', 'stars': 5, 'comment': 'نظيف'})
        self.assertEqual(response.status_code, 400)
        gen.make_reply.assert_not_called()

    def test_drain_requires_secret(self):
        with patch.dict(os.environ, {'CRON_SECRET':'test-secret'}):
            response = self.client.post('/internal/drain')
        self.assertEqual(response.status_code, 401)

    def test_liveness_does_not_claim_api_health(self):
        response=self.client.get('/live')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json()['google_reviews_api'],'not_checked')

    def test_health_identifies_missing_gemini_without_exposing_secrets(self):
        from unittest.mock import MagicMock
        fake = MagicMock()
        fake.counts.return_value = {'posted': 1}
        env = {
            'BRANCH_NAMES_JSON': json.dumps({
                'accounts/12/locations/1': 'فلور 1',
                'accounts/12/locations/2': 'فلور 2',
                'accounts/12/locations/3': 'فلور 3',
                'accounts/12/locations/4': 'فلور 4',
            }),
            'DATABASE_URL': 'postgresql://secret:password@host.example/db',
            'PUBSUB_AUDIENCE': 'https://example.com/pubsub',
            'PUBSUB_SERVICE_ACCOUNT_EMAIL': 'pubsub@example.com',
            'GBP_REFRESH_TOKEN': 'private-refresh-token',
            'GBP_CLIENT_ID': 'private-client-id',
            'GBP_CLIENT_SECRET': 'private-client-secret',
            'GEMINI_API_KEY': '',
            'AUTO_REPLY_ENABLED': 'false',
        }
        with patch.dict(os.environ, env), \
             patch.object(self.app_module, 'get_store', return_value=fake):
            result = self.client.get('/health')
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.get_json()['missing_components'], ['gemini'])
        self.assertNotIn('private', result.get_data(as_text=True))
        self.assertNotIn('password', result.get_data(as_text=True))

    def test_health_all_config_groups_present_still_does_not_assert_google_readiness(self):
        from unittest.mock import MagicMock
        fake = MagicMock()
        fake.counts.return_value = {'posted': 1}
        env = {
            'BRANCH_NAMES_JSON': json.dumps({
                'accounts/12/locations/1': 'فلور 1',
                'accounts/12/locations/2': 'فلور 2',
                'accounts/12/locations/3': 'فلور 3',
                'accounts/12/locations/4': 'فلور 4',
            }),
            'DATABASE_URL': 'postgresql://secret:password@host.example/db',
            'PUBSUB_AUDIENCE': 'https://example.com/pubsub',
            'PUBSUB_SERVICE_ACCOUNT_EMAIL': 'pubsub@example.com',
            'GBP_REFRESH_TOKEN': 'private-refresh-token',
            'GBP_CLIENT_ID': 'private-client-id',
            'GBP_CLIENT_SECRET': 'private-client-secret',
            'GEMINI_API_KEY': 'fake-test-api-key',
            'AUTO_REPLY_ENABLED': 'false',
        }
        with patch.dict(os.environ, env), \
             patch.object(self.app_module, 'get_store', return_value=fake):
            result = self.client.get('/health')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()['missing_components'], [])
        self.assertEqual(result.get_json()['google_reviews_api'], 'not_checked')
        self.assertFalse(result.get_json()['auto_reply_enabled'])
        self.assertNotIn('fake-test-api-key', result.get_data(as_text=True))

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
