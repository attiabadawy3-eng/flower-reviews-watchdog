# FLOWER Reviews Direct V6 (RC2)

**Status (7 November 2026):** isolated developer build; GitHub Actions: **40/40 tests passed with zero failures and zero skips**. Separate Render staging deployment is **live**, with only liveness configured. It **cannot read or reply to real Google reviews** until Google restores the existing project's GBP Reviews v4 API access, and an independent database/credentials are configured.

## Verified deployment
- GitHub branch: `feature/flower-reviews-v6-safety-20261107`; Draft PR #3; production `main` not modified.
- Staging endpoint: `https://flower-reviews-v6-staging.onrender.com/live` returns 200 and `google_reviews_api:not_checked`.
- `/health` returns **503** while database and credentials are absent; this is expected fail-closed readiness, not a deployment failure.
- Auto-post **disabled**: `AUTO_REPLY_ENABLED=false`, `OWNER_EXPRESS_CONSENT=false`.
- CI workflow: `.github/workflows/flower-v6-staging-ci.yml`.
- No Gmail, scraping, or browser-based review ingestion.
- Google Google Cloud project: `nice-etching-508014-m5` / `37036880095`. Existing API support case `9-3628000041274`.

## End-to-end design
1. Google Business Profile `NEW_REVIEW` or `UPDATED_REVIEW` event arrives via a **new independently authenticated Google Pub/Sub push subscription**.
2. Verify Google OIDC audience and sender; persist review identity in a durable PostgreSQL queue before acknowledging.
3. Official Google Business Profile Reviews API fetches review text, rating, branch and whether reply already exists.
4. Optional Gemini model writes a brief, natural Saudi hospitality response specific to the review. No static auto-publish fallback.
5. Never auto-publish old/edited/3-or-fewer-star/high-risk reviews; they enter manual review.
6. Only after owner opt-in, post one reply to eligible new 4/5-star reviews; persist write intent BEFORE the external request.
7. Verify Google readback. Ambiguous writes never reissue PUT automatically. After retention period, keep irreversible dedupe hashes.

## Actual test evidence
GitHub Actions initial full CI run `42416836718`, job `128536660223`: `RESULT tests=40 errors=0 failures=0 skipped=0`. Later read-only regression workflow also passed. These tests mock Google and AI interactions; **they do not prove production GBP credentials/permissions, model quality, or 24/7 uptime**.

## Deployment prerequisites
1. Google support resolves the contradictory allowlist state: support email says project is not approved, but Google's official application flow rejects a new request with `project number 37036880095 is already allowlisted`. Do not replace OAuth or create a different Cloud project without resolution.
2. Provision verified durable PostgreSQL with secure backups and privacy requirements; no Render ephemeral disk or 30-day trial database for critical records.
3. Store Google OAuth, Gemini key and Pub/Sub service-account configuration privately. Validate four genuine IDs and independent subscription.
4. Run live signed Pub/Sub ingestion, real Google GET and controlled single PUT/readback, then 24-hour verification. No auto-post cutover until all pass.
5. Cost/latency caveat: Render free plan can sleep after idle; low-cost/free tier does **not** guarantee second-level always-on responses.

Available endpoints: `GET /live` (liveness only), `GET /health` (readiness), `POST /pubsub/reviews` (authenticated push), `POST /internal/drain` (private cron token), `POST /internal/backfill` (explicit manual recovery, not auto-post).

**Do not merge PR #3 into `main` or connect the old production subscription until the gates are proven.**
## 2026-11-10 changes (patch on this branch; revised after review CHANGES_REQUESTED)
- **Five stars only:** automatic publication of `NEW_REVIEW` requires 5 stars. `AUTO_REPLY_MIN_STARS` below 5 is raised to 5 in code (`core.effective_minimum_stars`); 1–4 star reviews always go to human review.
- **2026 backfill:** `POST /internal/backfill-2026` (CRON secret), body `{"mode": ...}`:
  - `dry_run`: reads every page of all four branches; per-branch counts of unanswered 2026 (Asia/Riyadh) five-star candidates and how each relates to the existing ledger (`new`, `requalifiable`, `held_uncertain_write`, `in_flight`, `posted_by_v6`, `external_reply_recorded`, ...). Zero Google writes and zero database writes.
  - `canary` + `"review_name"`: exactly one owner-approved review. Requires `BACKFILL_CANARY_REVIEW` equal to that review and `OWNER_EXPRESS_CONSENT=true`, and is **refused while `AUTO_REPLY_ENABLED=true`**. The canary authorizes that one review only; it does not enable `NEW_REVIEW` publication or any other backfill job.
  - `publish`: refused (409) unless `BACKFILL_PUBLISH_ENABLED=true`, `OWNER_EXPRESS_CONSENT=true` and one canary reply is already confirmed by Google readback. Does not require or enable `AUTO_REPLY_ENABLED`.
  - Existing ledger rows: `approval_required` rows that never armed a write are atomically requalified; rows whose PUT may have happened (`write delivery uncertain`), `write_intent`, `verify_pending` and `processing` are never re-sent. Each review is re-read before writing; write intent and verify-only recovery are unchanged.
  - `POST /internal/backfill-2026/report`: per-branch status counts (`posted` = confirmed by readback).
- **Monitoring:** `v6/monitor_probe.py` requires `status=google_reads_verified`, integer `branches_checked==4` and an integer `google_writes==0` that is present. The scheduled probe and the legacy watchdog fix live in a **separate read-only patch for `main`** (scheduled workflows only run from the default branch); this branch contains no workflow changes.
