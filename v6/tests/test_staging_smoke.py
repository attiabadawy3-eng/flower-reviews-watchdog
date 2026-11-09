import logging
import os
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

from staging_smoke import run_smoke_once, maybe_start_smoke


class _FakeCursor:
    def __init__(self, row):
        self.row = row
    def fetchone(self):
        return self.row


class _FakeDatabase:
    def __init__(self):
        self.rows = set()
        self.preview_by_id = {}
        self.statements = []
    def execute(self, query, params=None):
        self.statements.append(query)
        if query.startswith("INSERT"):
            rid = params[0]
            if rid in self.rows:
                return _FakeCursor(None)
            self.rows.add(rid)
            return _FakeCursor((rid,))
        if query.startswith("UPDATE v6_smoke_checks SET preview_text"):
            self.preview_by_id[params[1]] = params[0]
        return _FakeCursor(None)


class _FakeStore:
    is_postgres = True
    def __init__(self):
        self.db = _FakeDatabase()
    @contextmanager
    def connection(self):
        yield self.db


class StagingSmokeTests(unittest.TestCase):
    def setUp(self):
        self.log = Mock()

    def test_one_real_synthetic_draft_attempt_no_second_inference(self):
        store = _FakeStore()
        gen = Mock()
        gen.make_reply.return_value = "حياك الله، نشكرك على تقييمك ويسعدنا زيارتك لفلور."
        with patch.dict(os.environ, {"AUTO_REPLY_ENABLED": "false"}):
            self.assertEqual(run_smoke_once(lambda: store, lambda: gen, self.log,
                                            "smoke-test-12345678"), "passed")
            self.assertEqual(run_smoke_once(lambda: store, lambda: gen, self.log,
                                            "smoke-test-12345678"), "already_attempted")
        gen.make_reply.assert_called_once()
        self.assertEqual(len(store.db.rows), 1)
        self.assertEqual(store.db.preview_by_id["smoke-test-12345678"],
                         gen.make_reply.return_value)

    def test_complaint_uses_synthetic_branch_and_negative_review_without_google(self):
        store = _FakeStore()
        gen = Mock()
        gen.make_reply.return_value = (
            "حياك الله، نأسف إن تجربتك ما كانت بالمستوى اللي تطمح له. "
            "نتمنى تتواصل مع الإدارة عبر القنوات الرسمية لمراجعة ملاحظتك."
        )
        with patch.dict(os.environ, {
            "AUTO_REPLY_ENABLED": "false",
            "AI_SMOKE_SCENARIO": "complaint",
        }):
            result = run_smoke_once(lambda: store, lambda: gen, self.log,
                                    "smoke-test-complaint-01")
        self.assertEqual(result, "passed")
        kwargs = gen.make_reply.call_args.kwargs
        self.assertEqual(kwargs["stars"], 2)
        self.assertEqual(kwargs["branch"], "فلور 2 السلام")
        self.assertIn("المكيف", kwargs["comment"])
        self.assertEqual(store.db.preview_by_id["smoke-test-complaint-01"],
                         gen.make_reply.return_value)

    def test_fails_closed_if_auto_reply_active(self):
        generator = Mock()
        with patch.dict(os.environ, {"AUTO_REPLY_ENABLED": "true"}):
            self.assertEqual(run_smoke_once(_FakeStore, lambda: generator, self.log,
                                            "smoke-test-12345678"), "disabled_for_live")
        generator.assert_not_called()

    def test_bad_id_rejected_before_db_or_inference(self):
        store = Mock()
        with patch.dict(os.environ, {"AUTO_REPLY_ENABLED": "false"}):
            self.assertEqual(run_smoke_once(store, Mock(), self.log, "bad/id"),
                             "invalid_id")
        store.assert_not_called()

    def test_no_start_by_default(self):
        with patch.dict(os.environ, {"AI_SMOKE_TEST_ID": ""}):
            self.assertFalse(maybe_start_smoke(Mock(), Mock(), self.log))

    def test_provider_error_logs_http_code_not_secret(self):
        store = _FakeStore()
        generator = Mock()
        generator.make_reply.side_effect = RuntimeError(
            "AI inference unavailable: HTTP 429 - SECRET-DO-NOT-LOG")
        with patch.dict(os.environ, {"AUTO_REPLY_ENABLED": "false"}):
            self.assertEqual(run_smoke_once(lambda: store, lambda: generator,
                                            self.log, "smoke-test-429-00001"), "failed")
        event = self.log.warning.call_args
        self.assertIn("429", str(event.args))
        self.assertNotIn("SECRET-DO-NOT-LOG", str(event.args))

    def test_store_error_does_not_generate_draft(self):
        def bad_store():
            raise RuntimeError("internal-db-path/secret")
        generator = Mock()
        with patch.dict(os.environ, {"AUTO_REPLY_ENABLED": "false"}):
            self.assertEqual(run_smoke_once(bad_store, lambda: generator,
                                            self.log, "smoke-test-12345678"), "storage_failed")
        generator.assert_not_called()


if __name__ == "__main__":
    unittest.main()
