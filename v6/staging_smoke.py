"""One-shot, non-posting Gemini inference smoke test for FLOWER V6 staging only.

Never reads or prints API keys. Records a run ID in Neon before attempting one
synthetic draft; restarts cannot repeat the request with the same ID.
"""
import os
import re
import threading
import time

_RUN_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{8,80}$")


def run_smoke_once(store_factory, generator_factory, logger, run_id):
    """Returns an opaque status, and never invokes Google Business Profile."""
    if not _RUN_ID_RE.fullmatch(str(run_id or "")):
        logger.warning("STAGING_AI_SMOKE_BLOCKED_INVALID_ID")
        return "invalid_id"
    if os.getenv("AUTO_REPLY_ENABLED") == "true":
        logger.warning("STAGING_AI_SMOKE_BLOCKED_AUTO_REPLY_ACTIVE")
        return "disabled_for_live"
    try:
        store = store_factory()
        if not store.is_postgres:
            logger.warning("STAGING_AI_SMOKE_BLOCKED_NON_POSTGRES")
            return "non_postgres"
        with store.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS v6_smoke_checks (
                run_id TEXT PRIMARY KEY,
                started_at DOUBLE PRECISION NOT NULL,
                preview_text TEXT
            )""")
            db.execute("ALTER TABLE v6_smoke_checks ADD COLUMN IF NOT EXISTS preview_text TEXT")
            row = db.execute("""INSERT INTO v6_smoke_checks(run_id,started_at)
                VALUES (%s,%s) ON CONFLICT(run_id) DO NOTHING RETURNING run_id""",
                (run_id, time.time())).fetchone()
        if not row:
            logger.info("STAGING_AI_SMOKE_ALREADY_ATTEMPTED run_id=%s", run_id)
            return "already_attempted"
    except Exception as exc:
        logger.warning("STAGING_AI_SMOKE_STORAGE_ERROR type=%s", type(exc).__name__)
        return "storage_failed"
    try:
        draft = generator_factory().make_reply(
            branch="فلور 1 العنود", stars=5,
            comment="استقبال ممتاز، الشقة نظيفة والمكان هادي، شكراً لكم.",
            recent=[])
        if not draft or len(draft) > 350:
            raise ValueError("draft length out of bounds")
        # Synthetic output only. Keep private in Neon for quality review; no client review is stored.
        with store.connection() as db:
            db.execute("UPDATE v6_smoke_checks SET preview_text=%s WHERE run_id=%s",
                       (draft, run_id))
        logger.info("STAGING_AI_SMOKE_PASS run_id=%s text_chars=%d", run_id, len(draft))
        return "passed"
    except Exception as exc:
        # Error class and three-digit provider code only; never log body or key.
        status = re.search(r"HTTP (\d{3})", str(exc))
        logger.warning("STAGING_AI_SMOKE_FAILED run_id=%s type=%s provider_http=%s",
                       run_id, type(exc).__name__,
                       status.group(1) if status else "none")
        return "failed"


def maybe_start_smoke(store_factory, generator_factory, logger):
    run_id = os.getenv("AI_SMOKE_TEST_ID", "").strip()
    if not run_id:
        return False
    if not _RUN_ID_RE.fullmatch(run_id):
        logger.warning("STAGING_AI_SMOKE_INVALID_RUN_ID")
        return False
    if os.getenv("AUTO_REPLY_ENABLED") == "true":
        logger.warning("STAGING_AI_SMOKE_BLOCKED_AUTO_REPLY_ACTIVE")
        return False
    thread = threading.Thread(
        target=run_smoke_once,
        args=(store_factory, generator_factory, logger, run_id),
        name="flower-v6-ai-smoke", daemon=True)
    thread.start()
    return True
