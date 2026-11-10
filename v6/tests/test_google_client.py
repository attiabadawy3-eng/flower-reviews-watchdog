"""Google OAuth cache tests: no real credentials and no network."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('GBP_CLIENT_ID', 'test-client')
os.environ.setdefault('GBP_CLIENT_SECRET', 'test-secret')
os.environ.setdefault('GBP_REFRESH_TOKEN', 'test-refresh')
import google_client


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload

    def json(self):
        return self.payload


class TokenCacheTests(unittest.TestCase):
    def setUp(self):
        self.client = google_client.GoogleClient()
        self.refresh_calls = 0

        def refresh(url, **kwargs):
            self.refresh_calls += 1
            return FakeResponse(200, {'access_token': 'token-' + str(self.refresh_calls), 'expires_in': 3600})

        self.client.session.post = refresh

    def test_token_reused_and_refreshed_after_expiry(self):
        with mock.patch.object(google_client.time, 'monotonic', return_value=1000):
            self.assertEqual([self.client.access_token() for _ in range(12)], ['token-1'] * 12)
        self.assertEqual(self.refresh_calls, 1)
        with mock.patch.object(google_client.time, 'monotonic', return_value=4600):
            self.assertEqual(self.client.access_token(), 'token-2')
        self.assertEqual(self.refresh_calls, 2)

    def test_failed_refresh_fails_closed(self):
        self.client.session.post = lambda *args, **kwargs: FakeResponse(400, {})
        with self.assertRaises(google_client.GoogleAPIError):
            self.client.access_token()
        self.assertIsNone(self.client._token)

    def test_missing_token_fails_closed(self):
        self.client.session.post = lambda *args, **kwargs: FakeResponse(200, {})
        with self.assertRaises(google_client.GoogleAPIError):
            self.client.access_token()
        self.assertIsNone(self.client._token)


if __name__ == '__main__':
    unittest.main()
