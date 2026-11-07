# V6 release and rollback gates — verified as of 2026-11-07

## Passed
- [x] Full RC2 source uploaded to isolated GitHub branch with verified SHA-256 before materialization.
- [x] GitHub Actions **40/40 tests**, no failures/skips; syntax compiled.
- [x] GitHub read-only regression workflow runs successfully.
- [x] Independent Render free Python staging service deployed **live**.
- [x] External `GET /live` returns JSON with `status=alive`; no Google permission success claimed.
- [x] External `GET /health` returns HTTP 503 with missing durable DB and credentials; fail-closed behavior.
- [x] No credentials configured, owner auto-reply consent remains false, and production service unchanged.

## Must pass before connecting live events
- [ ] Confirm Google Reviews v4 LIST, GET and UPDATE-REPLY entitlement for project 37036880095; no 404 or 429. Existing support case 9-3628000041274.
- [ ] Provision durable, isolated PostgreSQL and verified backup/recovery, honoring 0 SAR monthly cost.
- [ ] Configure least-privilege secret storage for GBP OAuth client, refresh token, Gemini key and cron token; no source files.
- [ ] Verify real branch and notification location mappings for all four branches, and exact account ownership.
- [ ] Create separate authenticated Pub/Sub push subscription and service account without changing old production subscriber; signed audience validation.
- [ ] Test signed inbound event and durable persistence across restart; forged token 401; malformed payload 400; duplicate review once.
- [ ] Confirm actual Gemini API model availability, quotas and privacy, and human-review 20 replies (including serious complaints).
- [ ] Obtain explicit owner policy authorization (which ratings to auto-post); sensitive/old/updated always require review.
- [ ] Prove one real Google read, one carefully controlled reply and readback. Confirm no second PUT even after timeout/restart.
- [ ] Prove four branch coverage and 24-hour no-repeat/latency metrics before cutover. Keep old history for rollback.

## Safety
- No Gmail as ingestion source; no unsupported GBP scraping/click automation; don't bypass Google API grant.
- Never mistake a Pub/Sub 204 or Render 200 for successful Google Reviews API read/write.
- Render free instance can sleep; no guaranteed instant replies while sleeping.
- Fail-closed on missing DB, OAuth, Google 404/429 and AI errors. Don't automatically retry uncertain outbound writes.
- Release flag default OFF. Production remains unchanged until evidence for every gate.

GitHub PR: https://github.com/attiabadawy3-eng/flower-reviews-watchdog/pull/3
Staging: https://flower-reviews-v6-staging.onrender.com/live
Google full CI: https://github.com/attiabadawy3-eng/flower-reviews-watchdog/actions/runs/42416836718
