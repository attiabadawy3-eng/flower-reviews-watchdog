# FLOWER Google Reviews — Saudi reply quality (DEV only)

**Status:** Staged code and tests, NOT connected to the live Render service.

The live Render service builds app.py from APP_CODE_GZ_B64, not this repo. An older **offline DEV snapshot** of the entire app was found on the authorized Sara PC under C:\\Users\\admin\\AppData\\Local\\SaraBridge\\work\\core2-rc-live\\snapshots\\flower_reviews_app_v52.py (153,156 bytes, 2,415 lines), with composer and regression test artifacts in sibling tools/ and results/. It implements 5.2 Reply Intelligence and also contains Google publishing calls: do NOT deploy as is. Live Render logs confirm /public/review-analytics/... HTTP 200, but this route is absent from the older snapshot's 29-route inventory. The snapshot is therefore **not verified identical to live 5.1**. Replacing APP_CODE_GZ_B64 blindly could remove live features. A permitted read-only export of the CURRENT Render app version is required for an exact diff before production integration.

**Real Windows DEV smoke test (2026-10-14):** 9/9 unittest methods passed on Sara PC; 16 simulated Saudi reply examples plus anti-duplication and unsupported-claim cases. No production mutation or Google write.

## Integration when production source is available

1. Use the existing generator to produce 2–4 relevant, Saudi-native candidate replies per review. This module does not generate text from static templates.
2. Import "select_safe_draft" from "review_quality/reply_quality.py" and provide the review text, 1–5 rating, candidate drafts, and last 50 replies for the SAME FLOWER branch. Names must be confirmed from the guest's own review or verified context.
3. A declined draft means regenerate or queue for human editing. An accepted draft is NOT a publish authorization.
4. Preserve per-review ID, branch ID, rating, source text, quality reasons, the chosen draft and the owner's decision in the existing secure storage. Do not copy reviews, customer data, or credentials into GitHub.
5. Review at least 20 real anonymized examples from all four branches plus the last 50 existing replies per branch. Compare openings, closings, repetition and factual accuracy; test idempotency, pending-queue behavior and a real Google publishing read-back in a separately approved production pilot.
6. All new Google replies remain draft / human-approval only. Do not edit existing replies or activate automatic posting without a separate owner authorization.

## FLOWER's Saudi tone

- Warm, idiomatic Saudi: "يا هلا", "حياك الله", "نورتنا", "سعدنا" used naturally, **not** identically for every guest. Distinguish review-less 5-star feedback, a detailed compliment, a mixed review, and a serious complaint.
- Thank guests for specific positive points that they ACTUALLY mentioned. Mention employees only when named and confirmed, and avoid unsolicited personal details.
- For criticism, acknowledge the specific problem and apologize without blaming guests or promising unsupported remedies. Never assert "تم حل المشكلة", "تم التواصل معك", "تم اتخاذ الإجراءات" unless confirmed; the gate blocks several common unsupported claims.
- Avoid canned marketing slogans, repeated WhatsApp/contact details, formal corporate signatures and formulaic endings.
- 0–2 subtle emojis in positive replies; none for serious complaints.
- Adapt length to feedback (a short rating warrants a short reply). Human reviewers remain responsible for correctness, policy and tone.

## Tests

Run from the review_quality directory:

    python -m unittest discover -s tests -v

Dependency-free Python standard library; no Google API calls; no secrets; no app changes; no background processes.

## Scope of this change

Adds only a draft-quality evaluator, test suite and these integration instructions. It does NOT claim production integration or test replies against live historical data. Next step is retrieving the actual Render app source and reviewing the real last-50 responses (all branches), not deploying this module blindly.