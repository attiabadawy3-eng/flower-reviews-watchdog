"""Monitor never reports green without real Google reads; 2026 backfill route gates."""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from monitor_probe import evaluate

MAPPING = {f'accounts/12/locations/{i}': f'فلور {i}' for i in range(1, 5)}


class MonitorTests(unittest.TestCase):
    def test_green_only_on_verified_reads_all_branches(self):
        code, msg = evaluate(200, {'status': 'google_reads_verified', 'branches_checked': 4, 'google_writes': 0})
        self.assertEqual(code, 0, msg)

    def test_google_404_is_red(self):
        code, msg = evaluate(502, {'status': 'google_api_unavailable', 'provider_http': 404, 'google_writes': 0})
        self.assertEqual(code, 1)
        self.assertIn('404', msg)

    def test_http_200_without_verification_is_red(self):
        for body in ({'service': 'flower-reviews-v6', 'status': 'alive', 'google_reviews_api': 'not_checked'},
                     {'status': 'google_reads_verified', 'branches_checked': 3, 'google_writes': 0},
                     {}, None):
            self.assertEqual(evaluate(200, body)[0], 1, body)

    def test_missing_or_mistyped_proof_fields_are_red(self):
        base = {'status': 'google_reads_verified', 'branches_checked': 4, 'google_writes': 0}
        for change in ({'google_writes': None}, {'google_writes': '0'}, {'google_writes': False},
                       {'branches_checked': '4'}, {'branches_checked': True}, {'branches_checked': 4.0}):
            body = dict(base, **change)
            body = {k: v for k, v in body.items() if v is not None}
            self.assertEqual(evaluate(200, body)[0], 1, change)
        # The exact contract still passes.
        self.assertEqual(evaluate(200, base)[0], 0)

    def test_probe_reporting_writes_is_red(self):
        self.assertEqual(evaluate(200, {'status': 'google_reads_verified', 'branches_checked': 4,
                                        'google_writes': 1})[0], 1)

    def test_missing_configuration_is_not_green(self):
        import monitor_probe
        with patch.dict(os.environ, {'V6_BASE_URL': '', 'V6_CRON_SECRET': ''}):
            self.assertEqual(monitor_probe.main(), 2)


try:
    import flask  # noqa: F401
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False


@unittest.skipUnless(HAS_FLASK, 'Flask not installed')
class Backfill2026RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app as app_module
        cls.app_module = app_module

    def setUp(self):
        self.client = self.app_module.app.test_client()
        self.auth = {'Authorization': 'Bearer s3cret'}

    def post(self, body, env=None, google=None):
        env = {'CRON_SECRET': 's3cret', 'BRANCH_NAMES_JSON': json.dumps(MAPPING), **(env or {})}
        with patch.dict(os.environ, env), \
             patch.object(self.app_module, 'GoogleClient', return_value=google or MagicMock()), \
             patch.object(self.app_module, 'get_store') as store:
            store.return_value.job_info.return_value = (None, None, '')  # empty ledger
            store.return_value.verified_post_count.return_value = 0
            response = self.client.post('/internal/backfill-2026', json=body, headers=self.auth)
        return response, store

    def test_requires_secret(self):
        with patch.dict(os.environ, {'CRON_SECRET': 's3cret'}):
            self.assertEqual(self.client.post('/internal/backfill-2026', json={}).status_code, 401)
            self.assertEqual(self.client.post('/internal/backfill-2026/report').status_code, 401)

    def test_invalid_mode(self):
        response, _ = self.post({'mode': 'everything'})
        self.assertEqual(response.status_code, 400)

    def test_dry_run_reads_only_and_never_touches_storage(self):
        g = MagicMock()
        g.list_reviews.side_effect = lambda location, page_token=None: {'reviews': [
            {'name': location + '/reviews/r1', 'starRating': 'FIVE',
             'createTime': '2026-04-01T10:00:00Z'}]}
        response, store = self.post({'mode': 'dry_run'}, google=g)
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body['google_writes'], 0)
        self.assertEqual(body['database_writes'], 0)
        self.assertEqual(body['totals']['candidates'], 4)  # one per branch
        self.assertEqual(body['branches']['accounts/12/locations/2']['candidates'], 1)
        # Ledger is read only: no enqueue, requalify or finish.
        ledger = store.return_value
        ledger.enqueue.assert_not_called()
        ledger.requalify_for_backfill_2026.assert_not_called()
        ledger.finish.assert_not_called()
        g.reply.assert_not_called()

    def test_dry_run_still_reports_when_storage_down(self):
        g = MagicMock()
        g.list_reviews.return_value = {'reviews': []}
        env = {'CRON_SECRET': 's3cret', 'BRANCH_NAMES_JSON': json.dumps(MAPPING)}
        with patch.dict(os.environ, env), \
             patch.object(self.app_module, 'GoogleClient', return_value=g), \
             patch.object(self.app_module, 'get_store', side_effect=RuntimeError('db down')):
            response = self.client.post('/internal/backfill-2026', json={'mode': 'dry_run'}, headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['ledger_by_branch'], 'storage_unavailable')

    def test_canary_requires_review_name(self):
        response, _ = self.post({'mode': 'canary'})
        self.assertEqual(response.status_code, 400)
        response, _ = self.post({'mode': 'canary', 'review_name': 'not-a-review'})
        self.assertEqual(response.status_code, 400)

    def test_empty_branch_name_rejected(self):
        bad = dict(MAPPING, **{'accounts/12/locations/4': ''})
        response, _ = self.post({'mode': 'dry_run'}, env={'BRANCH_NAMES_JSON': json.dumps(bad)})
        self.assertEqual(response.status_code, 503)

    def test_google_404_reported_as_failure(self):
        from google_client import GoogleAPIError
        g = MagicMock()
        g.list_reviews.side_effect = GoogleAPIError(404, 'Method not found')
        response, _ = self.post({'mode': 'dry_run'}, google=g)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()['provider_http'], 404)

    def test_canary_blocked_by_default_flags(self):
        g = MagicMock()
        g.list_reviews.return_value = {'reviews': []}
        name = 'accounts/12/locations/1/reviews/r1'
        # Owner consent missing by default -> blocked.
        response, _ = self.post({'mode': 'canary', 'review_name': name},
                                env={'BACKFILL_CANARY_REVIEW': name}, google=g)
        self.assertEqual(response.status_code, 409)
        # General switch on -> canary refused even with consent.
        response, _ = self.post({'mode': 'canary', 'review_name': name},
                                env={'BACKFILL_CANARY_REVIEW': name, 'OWNER_EXPRESS_CONSENT': 'true',
                                     'AUTO_REPLY_ENABLED': 'true'}, google=g)
        self.assertEqual(response.status_code, 409)
        self.assertIn('AUTO_REPLY_ENABLED', response.get_json()['reason'])
        g.reply.assert_not_called()

    def test_process_one_passes_backfill_auth_not_general_switch(self):
        """App wiring: a NEW_REVIEW job never receives canary/bulk authorization."""
        store = MagicMock()
        store.verified_post_count.return_value = 5
        with patch.dict(os.environ, {'BACKFILL_CANARY_REVIEW': 'accounts/1/locations/1/reviews/x',
                                     'BACKFILL_PUBLISH_ENABLED': 'true'}):
            new = self.app_module.backfill_authorization(store, {'event_type': 'NEW_REVIEW'})
            old = self.app_module.backfill_authorization(store, {'event_type': 'BACKFILL_2026'})
        self.assertEqual(new, {'backfill_canary_review': None, 'backfill_bulk_authorized': False})
        self.assertTrue(old['backfill_bulk_authorized'])


if __name__ == '__main__':
    unittest.main()
