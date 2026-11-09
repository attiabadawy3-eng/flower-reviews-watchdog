"""Validation tests for real-Postgres acceptance runner; no database connection."""
import unittest

from postgres_acceptance import validate_direct_neon_url


class NeonDatabasePreflightTests(unittest.TestCase):
    def test_direct_neon_with_tls_is_allowed(self):
        valid = ('postgresql://flower:test-pass@ep-test.us-east-2.aws.neon.tech/'
                 'flower_reviews?sslmode=require')
        self.assertTrue(validate_direct_neon_url(valid))

    def test_connection_pooler_rejected_for_schema_creation(self):
        pooled = ('postgresql://flower:test-pass@ep-test-pooler.us-east-2.aws.neon.tech/'
                  'flower_reviews?sslmode=require')
        with self.assertRaises(ValueError):
            validate_direct_neon_url(pooled)

    def test_non_neon_database_rejected(self):
        other = 'postgresql://flower:test-pass@postgres.example.com/flower_reviews?sslmode=require'
        with self.assertRaises(ValueError):
            validate_direct_neon_url(other)

    def test_no_ssl_rejected(self):
        unencrypted = ('postgresql://flower:test-pass@ep-test.us-east-2.aws.neon.tech/'
                       'flower_reviews?sslmode=disable')
        with self.assertRaises(ValueError):
            validate_direct_neon_url(unencrypted)

    def test_missing_connection_fails_closed(self):
        with self.assertRaises(ValueError):
            validate_direct_neon_url('')


if __name__ == '__main__':
    unittest.main()
