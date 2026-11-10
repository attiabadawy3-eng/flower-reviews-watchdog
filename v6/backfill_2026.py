"""Backfill for unanswered five-star reviews published in 2026 (Saudi time).

Three modes, all behind the internal CRON secret:

* dry_run  - read every review page of all four branches and report counts,
             including how each candidate relates to the existing job ledger.
             Zero Google writes and zero database writes (ledger is read only).
* canary   - publish exactly ONE owner-approved review. Authorization is bound
             to that review: BACKFILL_CANARY_REVIEW must equal the requested
             review, OWNER_EXPRESS_CONSENT must be true, and the general
             NEW_REVIEW switch AUTO_REPLY_ENABLED must stay false during it.
* publish  - only after a canary reply is confirmed by Google readback, with a
             separate BACKFILL_PUBLISH_ENABLED authorization: queue every
             candidate (deduplicated in the database) and process a small batch.

The processor re-reads each review from Google before writing, persists write
intent before PUT, and only verifies (never re-PUTs) after an uncertain write.
"""
from core import REVIEW_PATTERN, LOCATION_PATTERN, ReviewEvent, classify_backfill_2026, UNCERTAIN_WRITE_ERROR

EVENT_TYPE = 'BACKFILL_2026'
REPORT_KEYS = ('scanned', 'candidates', 'already_replied', 'below_five', 'outside_2026', 'invalid', 'pages')
# How a scan candidate relates to the durable job ledger.
LEDGER_STATES = ('new', 'requalifiable', 'already_backfill_2026', 'posted_by_v6', 'external_reply_recorded',
                 'held_uncertain_write', 'in_flight', 'pending_other_path', 'tombstone_complete',
                 'tombstone_expired')


class BackfillIncomplete(RuntimeError):
    """Raised when a branch could not be read completely; counts would be wrong."""


class BackfillBlocked(RuntimeError):
    """Raised when a publication gate is not satisfied."""


def validate_branches(branches) -> dict:
    if not isinstance(branches, dict) or len(branches) != 4:
        raise ValueError('expected four verified location mappings')
    names = []
    for key, value in branches.items():
        if not isinstance(key, str) or not LOCATION_PATTERN.fullmatch(key):
            raise ValueError('invalid location resource in mapping')
        if not isinstance(value, str) or not value.strip():
            raise ValueError('branch name must be a non-empty string')
        names.append(value.strip())
    if len(set(names)) != 4:
        raise ValueError('branch names must be distinct')
    return branches


def scan(client, branches, *, now=None, max_pages_per_branch=200, details=None):
    """Read ALL pages for every branch. Returns (report, candidates).

    candidates: ordered list of (location, review_name), oldest review first.
    A partial read raises instead of returning an undercount.
    """
    validate_branches(branches)
    report, found = {}, []
    for location, branch_name in branches.items():
        row = {'branch': branch_name, **{key: 0 for key in REPORT_KEYS}}
        seen, page = set(), None
        while True:
            if row['pages'] >= max_pages_per_branch:
                raise BackfillIncomplete(f'page limit reached for {location}')
            response = client.list_reviews(location, page_token=page)
            row['pages'] += 1
            for review in response.get('reviews', []) or []:
                name = str((review or {}).get('name') or '')
                if not REVIEW_PATTERN.fullmatch(name) or not name.startswith(location + '/reviews/'):
                    row['invalid'] += 1
                    continue
                if name in seen:
                    continue  # the same review on two pages counts once
                seen.add(name)
                row['scanned'] += 1
                kind = classify_backfill_2026(review, now)
                if kind == 'candidate':
                    row['candidates'] += 1
                    found.append((review.get('createTime') or '', location, name))
                    if details is not None:
                        # Enough for the owner to recognise and approve one exact review.
                        details[name] = {
                            'review_name': name, 'branch': branch_name,
                            'create_time': review.get('createTime'),
                            'reviewer': str(((review.get('reviewer') or {}).get('displayName')) or '')[:60],
                            'comment_preview': ' '.join(str(review.get('comment') or '').split())[:160],
                        }
                else:
                    row[kind] += 1
            page = response.get('nextPageToken')
            if not page:
                break
        report[location] = row
    found.sort()
    return report, [(location, name) for _, location, name in found]


def totals(report) -> dict:
    return {key: sum(row[key] for row in report.values()) for key in REPORT_KEYS}


def ledger_state(store, review_name) -> str:
    status, event_type, error = store.job_info(review_name)
    if status is None:
        return 'new'
    if status == 'tombstone_complete':
        return 'tombstone_complete'
    if status == 'tombstone_expired':
        return 'tombstone_expired'
    if status == 'posted':
        return 'posted_by_v6'
    if status == 'existing':
        return 'external_reply_recorded'
    if status in ('write_intent', 'verify_pending', 'processing'):
        return 'in_flight'
    if status == 'approval_required':
        if error == UNCERTAIN_WRITE_ERROR:
            return 'held_uncertain_write'
        return 'already_backfill_2026' if event_type == EVENT_TYPE else 'requalifiable'
    if status in ('queued', 'retry'):
        return 'already_backfill_2026' if event_type == EVENT_TYPE else 'pending_other_path'
    return 'pending_other_path'


def ledger_report(store, candidates) -> tuple[dict, dict]:
    by_branch, states = {}, {}
    for location, name in candidates:
        state = ledger_state(store, name)
        states[name] = state
        row = by_branch.setdefault(location, {key: 0 for key in LEDGER_STATES})
        row[state] += 1
    return by_branch, states


def _admit(store, location, name, state, source):
    """Put one candidate on the 2026 path. Never touches a possibly-written job."""
    if state == 'new':
        return store.enqueue(ReviewEvent(name, location, EVENT_TYPE, source))
    if state == 'tombstone_expired':
        # Original job expired unresolved. Its external PUT history is unknown:
        # automatic re-admission could send a duplicate reply. Human audit only.
        return False
    if state == 'requalifiable':
        return store.requalify_for_backfill_2026(name)
    return False


def job_authorization(store, job, env) -> dict:
    """Per-job 2026 backfill authorization for the processor.

    Independent of AUTO_REPLY_ENABLED (which governs NEW_REVIEW only). A canary
    authorizes exactly one review resource; bulk needs its own flag AND a canary
    reply already confirmed by Google readback.
    """
    if job.get('event_type') != EVENT_TYPE:
        return {'backfill_canary_review': None, 'backfill_bulk_authorized': False}
    canary = env.get('BACKFILL_CANARY_REVIEW') or None
    bulk = (env.get('BACKFILL_PUBLISH_ENABLED') == 'true' and
            store.verified_post_count(EVENT_TYPE) >= 1)
    return {'backfill_canary_review': canary, 'backfill_bulk_authorized': bulk}


def run(mode, *, client, store, branches, process_one, env, now=None, batch=5, canary_review=None):
    """Execute one backfill request. process_one(review_name) processes a queued job."""
    if mode not in ('dry_run', 'canary', 'publish'):
        raise ValueError('mode must be dry_run, canary or publish')
    details = {} if mode == 'dry_run' else None
    report, candidates = scan(client, branches, now=now, details=details)
    result = {'mode': mode, 'branches': report, 'totals': totals(report)}
    if mode == 'dry_run':
        states = {}
        if store is not None:
            result['ledger_by_branch'], states = ledger_report(store, candidates)
        # Oldest first; capped so a large backlog cannot produce a huge response.
        result['candidate_list'] = [dict(details[name], ledger_state=states.get(name, 'unknown'))
                                    for _, name in candidates[:50]]
        result.update({'google_writes': 0, 'database_writes': 0})
        return result

    if env.get('OWNER_EXPRESS_CONSENT') != 'true':
        raise BackfillBlocked('OWNER_EXPRESS_CONSENT is not true')

    if mode == 'canary':
        if env.get('AUTO_REPLY_ENABLED') == 'true':
            raise BackfillBlocked('AUTO_REPLY_ENABLED must remain false during the canary')
        approved = env.get('BACKFILL_CANARY_REVIEW') or ''
        if not canary_review or canary_review != approved:
            raise BackfillBlocked('canary review must equal the owner-approved BACKFILL_CANARY_REVIEW')
        match = [(loc, name) for loc, name in candidates if name == canary_review]
        if not match:
            raise BackfillBlocked('approved canary review is not an unanswered 2026 five-star candidate')
        location, name = match[0]
        state = ledger_state(store, name)
        if not _admit(store, location, name, state, 'backfill-2026-canary'):
            raise BackfillBlocked(f'canary review cannot be admitted from ledger state {state}')
        process_one(name)
        result.update({'canary_review': name, 'canary_status': store.job_info(name)[0],
                       'confirmed_backfill_replies': store.verified_post_count(EVENT_TYPE)})
        return result

    # mode == 'publish'
    if env.get('BACKFILL_PUBLISH_ENABLED') != 'true':
        raise BackfillBlocked('BACKFILL_PUBLISH_ENABLED is not true')
    if store.verified_post_count(EVENT_TYPE) < 1:
        raise BackfillBlocked('bulk publication requires one canary reply confirmed by Google readback')
    ledger_before, states = ledger_report(store, candidates)
    admitted = 0
    for location, name in candidates:
        if _admit(store, location, name, states[name], 'backfill-2026-publish'):
            admitted += 1
    processed = 0
    for location, name in candidates:
        if processed >= batch:
            break
        status, event_type, _ = store.job_info(name)
        if event_type == EVENT_TYPE and status in ('queued', 'retry'):
            process_one(name)
            processed += 1
    result.update({'ledger_before': ledger_before, 'admitted': admitted, 'processed_now': processed,
                   'queue_by_branch': store.report_by_location(EVENT_TYPE),
                   'confirmed_backfill_replies': store.verified_post_count(EVENT_TYPE)})
    return result
