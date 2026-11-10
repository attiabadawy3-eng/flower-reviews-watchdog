"""Validation tests for real-Postgres acceptance runner; no database connection."""
import unittest

from postgres_acceptance import validate_direct_neon_url, isolated_schema_url
from storage import SCHEMA


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

    def test_schema_url_preserves_postgres_uri_with_ssl(self):
        base = ('postgresql://flower:test-pass@ep-test.us-east-2.aws.neon.tech/'
                'flower_reviews?sslmode=require')
        dsn = isolated_schema_url(base, 'flower_reviews_v6_acceptance_ab12')
        self.assertTrue(dsn.startswith('postgresql://'))
        self.assertIn('sslmode=require&options=', dsn)
        self.assertIn('-csearch_path%3Dflower_reviews_v6_acceptance_ab12', dsn)

    def test_schema_url_without_existing_query(self):
        base = 'postgresql://flower:test-pass@ep-test.us-east-2.aws.neon.tech/flower_reviews'
        dsn = isolated_schema_url(base, 'flower_reviews_test')
        self.assertTrue(dsn.startswith(base + '?options='))
        self.assertIn('-csearch_path%3Dflower_reviews_test', dsn)

    def test_lease_and_retry_timestamps_are_float8_not_float4(self):
        for column in ('next_try', 'lease_until', 'created_at', 'updated_at'):
            with self.subTest(column=column):
                self.assertIn(column + ' DOUBLE PRECISION NOT NULL', SCHEMA)
                self.assertNotIn(column + ' REAL NOT NULL', SCHEMA)

    def test_missing_connection_fails_closed(self):
        with self.assertRaises(ValueError):
            validate_direct_neon_url('')


if __name__ == '__main__':
    unittest.main()
