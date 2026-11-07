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