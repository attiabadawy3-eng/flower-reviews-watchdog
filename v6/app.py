"""Independent direct-Google event receiver. No Gmail or scraping.

Production is fail-closed until GBP Reviews API and durable DB access return.
"""
import base64
import hmac
import logging
import os
import re

from flask import Flask, request, jsonify
from core import parse_pubsub, InvalidNotification
from storage import Store
from google_client import GoogleClient
from ai import SaudiReplyGenerator
from core import REVIEW_PATTERN as REVIEW_NAME_RE

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 65536  # authenticated Pub/Sub envelopes only
logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'))
log = logging.getLogger('flower-v6')

# The store intentionally cannot initialize with an ephemeral database by default.
_store = None

def get_store():
    global _store
    if _store is None:
        _store = Store()
    return _store


def authenticate_pubsub(req):
    """Pub/Sub authenticated push with expected audience + service account identity."""
    audience = os.environ.get('PUBSUB_AUDIENCE')
    email = os.environ.get('PUBSUB_SERVICE_ACCOUNT_EMAIL')
    bearer = req.headers.get('Authorization','')
    if not audience or not email or not bearer.startswith('Bearer '):
        return False
    try:
        from google.oauth2 import id_token
        from google.auth.transport.requests import Request
        claims = id_token.verify_oauth2_token(bearer[7:], Request(), audience=audience)
        return claims.get('email') == email and claims.get('email_verified') is True
    except Exception:
        return False


def process_one(review_name=None, approved_text=None):
    store = get_store()
    job = store.claim(review_name)
    if not job:
        return False
    import json
    from processor import process_claimed_job
    from backfill_2026 import generator_plan, ApprovedTextGenerator
    aliases = json.loads(os.getenv('BRANCH_NAMES_JSON','{}'))
    plan, value = generator_plan(job, os.environ, approved_text)
    if plan == 'defer':
        # The canary review is never published with model text; leave it queued.
        store.retry(job['review_name'], job['attempts'], value)
        return False
    try:
        google_client = GoogleClient()
        ai_generator = ApprovedTextGenerator(value) if plan == 'approved' else SaudiReplyGenerator()
    except (KeyError, ValueError) as exc:
        store.retry(job['review_name'],job['attempts'], 'missing or invalid connector configuration')
        return False
    return process_claimed_job(
        job=job, store=store,
        google_client=google_client,
        ai_generator=ai_generator,
        branch_names=aliases,
        auto_enabled=os.getenv('AUTO_REPLY_ENABLED')=='true',
        owner_consent=os.getenv('OWNER_EXPRESS_CONSENT')=='true',
        minimum_stars=os.getenv('AUTO_REPLY_MIN_STARS', '4'),
        scope=os.getenv('AUTO_REPLY_SCOPE', 'positive'),
        **backfill_authorization(store, job),
    )


def backfill_authorization(store, job):
    from backfill_2026 import job_authorization
    return job_authorization(store, job, os.environ)


@app.get('/live')
def live():
    # Liveness is deliberately not confused with API permission readiness.
    return jsonify({'service':'flower-reviews-v6','status':'alive','google_reviews_api':'not_checked'}), 200


@app.get('/health')
def health():
    import json
    try:
        aliases = json.loads(os.getenv('BRANCH_NAMES_JSON','{}'))
        mapped = len(aliases) == 4 and all(isinstance(v,str) and v.strip() for v in aliases.values())
    except (ValueError,TypeError):
        mapped = False
    # Presence-only diagnostics: disclose no tokens, connection strings or key values.
    readiness = {
        'branches': mapped,
        'storage': bool(os.getenv('DATABASE_URL')),
        'pubsub': bool(os.getenv('PUBSUB_AUDIENCE') and
                       os.getenv('PUBSUB_SERVICE_ACCOUNT_EMAIL')),
        'google_oauth': bool(os.getenv('GBP_REFRESH_TOKEN') and
                             os.getenv('GBP_CLIENT_ID') and os.getenv('GBP_CLIENT_SECRET')),
        'gemini': bool(os.getenv('GEMINI_API_KEY')),
    }
    ready = all(readiness.values())
    try:
        counts = get_store().counts()
        # Readiness here means configuration/storage only. It NEVER claims that
        # Google v4 Reviews is healthy; that needs a confirmed real API call.
        return jsonify({'status':'configured_api_unverified' if ready else 'configuration_incomplete',
                        'configured':ready,'google_reviews_api':'not_checked',
                        'missing_components':[k for k, value in readiness.items() if not value],
                        'auto_reply_enabled':os.getenv('AUTO_REPLY_ENABLED')=='true',
                        'jobs':counts}),200 if ready else 503
    except Exception:
        return jsonify({'status':'storage_unavailable','ready':False}),503


@app.get('/health/storage')
def health_storage():
    """Storage-only readiness, separate from Google OAuth and publication readiness."""
    try:
        counts = get_store().counts()
        return jsonify({'status': 'storage_ready', 'database': 'postgres',
                        'auto_reply_enabled': os.getenv('AUTO_REPLY_ENABLED') == 'true',
                        'jobs': counts}), 200
    except Exception:
        log.warning('storage readiness failed', exc_info=False)
        return jsonify({'status': 'storage_unavailable'}), 503


def _internal_authorized(req):
    secret = os.getenv('CRON_SECRET', '')
    supplied = req.headers.get('Authorization', '').removeprefix('Bearer ')
    return bool(secret) and hmac.compare_digest(supplied, secret)


@app.post('/internal/oauth-client-check')
def oauth_client_check():
    """Check an uploaded dedicated desktop OAuth client without exposing its secrets.

    This verifies the file's shape only; it does not authorize Google access,
    replace existing credentials, or send a Google API request.
    """
    if not _internal_authorized(request):
        return jsonify({'error': 'unauthorized'}), 401
    import json
    path = '/etc/secrets/gbp_prod_client.json'
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return jsonify({'status': 'oauth_file_missing', 'google_writes': 0}), 503
    except (OSError, UnicodeError, ValueError):
        return jsonify({'status': 'oauth_file_unreadable', 'google_writes': 0}), 422

    c = data.get('installed') if isinstance(data, dict) else None
    if not isinstance(c, dict):
        return jsonify({'status': 'oauth_not_desktop_client', 'google_writes': 0}), 422
    cid, secret = c.get('client_id'), c.get('client_secret')
    if (c.get('project_id') != 'nice-etching-508014-m5' or
            not isinstance(cid, str) or
            not cid.startswith('37036880095-') or
            not cid.endswith('.apps.googleusercontent.com') or
            not isinstance(secret, str) or not secret):
        return jsonify({'status': 'oauth_project_or_fields_mismatch',
                        'google_writes': 0}), 422
    return jsonify({'status': 'production_desktop_client_file_verified',
                    'authorization': 'pending_user_consent',
                    'google_reads': 0, 'google_writes': 0,
                    'auto_reply_enabled': False}), 200


@app.post('/internal/google-probe')
def google_probe():
    """Safely verify Google Reviews API reads on all four locations. Zero writes."""
    if not _internal_authorized(request):
        return jsonify({'error': 'unauthorized'}), 401
    import json
    from core import LOCATION_PATTERN
    from google_client import GoogleAPIError
    try:
        aliases = json.loads(os.getenv('BRANCH_NAMES_JSON', '{}'))
        if (not isinstance(aliases, dict) or len(aliases) != 4 or
                not all(LOCATION_PATTERN.fullmatch(k) for k in aliases)):
            return jsonify({'status': 'branch_mapping_invalid', 'google_writes': 0}), 503
        client = GoogleClient()
        verified = 0
        for location in aliases:
            result = client.list_reviews(location)
            if not isinstance(result, dict) or not isinstance(result.get('reviews', []), list):
                return jsonify({'status': 'invalid_google_response', 'google_writes': 0}), 502
            verified += 1
        return jsonify({'status': 'google_reads_verified', 'branches_checked': verified,
                        'google_writes': 0, 'auto_reply_enabled':
                        os.getenv('AUTO_REPLY_ENABLED') == 'true'}), 200
    except GoogleAPIError as err:
        return jsonify({'status': 'google_api_unavailable',
                        'provider_http': err.status, 'google_writes': 0}), 502
    except Exception:
        log.warning('Google read-only probe failed', exc_info=False)
        return jsonify({'status': 'readiness_unavailable', 'google_writes': 0}), 503


@app.post('/internal/ai-preview')
def ai_preview():
    """Generate a synthetic/non-published reply draft for tone and model testing."""
    if not _internal_authorized(request):
        return jsonify({'error': 'unauthorized'}), 401
    import json
    try:
        body = request.get_json(silent=True)
        aliases = json.loads(os.getenv('BRANCH_NAMES_JSON', '{}'))
        if not isinstance(body, dict) or not isinstance(aliases, dict) or len(aliases) != 4:
            return jsonify({'error': 'invalid_request'}), 400
        branch = body.get('branch')
        stars = body.get('stars')
        comment = body.get('comment', '')
        if (branch not in aliases.values() or type(stars) is not int or
                not 1 <= stars <= 5 or not isinstance(comment, str) or len(comment) > 1000):
            return jsonify({'error': 'invalid_request'}), 400
        draft = SaudiReplyGenerator().make_reply(branch=branch, stars=stars,
                                                  comment=comment, recent=[])
        return jsonify({'status': 'draft_only', 'reply': draft,
                        'google_reads': 0, 'google_writes': 0}), 200
    except Exception:
        log.warning('AI preview unavailable', exc_info=False)
        return jsonify({'status': 'ai_unavailable', 'google_writes': 0}), 503


@app.post('/pubsub/reviews')
def receive():
    if not authenticate_pubsub(request):
        return jsonify({'error':'unauthorized'}),401
    try:
        import json
        aliases = json.loads(os.getenv('PUBSUB_LOCATION_ALIASES_JSON', '{}'))
        event = parse_pubsub(request.get_json(silent=True) or {},location_aliases=aliases)
    except (InvalidNotification, ValueError) as exc:
        return jsonify({'error':str(exc)}),400
    if event is None:
        return '',204
    try:
        is_new = get_store().enqueue(event)
    except Exception:
        log.exception('event was not durably recorded')
        return jsonify({'error':'storage_unavailable'}),503
    # Immediate execution, but Pub/Sub ACK is based on durable receipt, not
    # successful AI or Google API. A separate scheduler can drain retries.
    if is_new:
        try:
            process_one(event.review_name)
        except Exception:
            # Receipt was already durably committed: never NACK an accepted
            # message just because downstream processing crashed. A worker
            # can recover the expired claim later.
            log.exception('post-ingestion processing failed; stored job is retained')
    return '',204


@app.post('/internal/drain')
def drain():
    secret = os.getenv('CRON_SECRET','')
    supplied = request.headers.get('Authorization','').removeprefix('Bearer ')
    if not secret or not hmac.compare_digest(supplied,secret):
        return jsonify({'error':'unauthorized'}),401
    n=0
    store = get_store()
    store.prune_old()
    batch = min(10, int(os.getenv('MAX_DRAIN_BATCH','5')))
    released = []
    from core import auto_reply_scope
    if (auto_reply_scope(os.getenv('AUTO_REPLY_SCOPE')) == 'all' and
            os.getenv('AUTO_REPLY_ENABLED') == 'true' and os.getenv('OWNER_EXPRESS_CONSENT') == 'true'):
        released = store.release_held_reviews(limit=batch)
    for _ in range(batch):
        if not process_one():
            break
        n+=1
    return jsonify({'processed':n,'released':len(released),'jobs':store.counts()})


@app.post('/internal/backfill')
def backfill():
    """Explicit, authenticated recovery scan; NEVER automatically publishes."""
    secret = os.getenv('CRON_SECRET', '')
    supplied = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if not secret or not hmac.compare_digest(supplied, secret):
        return jsonify({'error':'unauthorized'}), 401
    if os.getenv('BACKFILL_ENABLED') != 'true':
        return jsonify({'error':'backfill_disabled'}), 403
    import json
    from core import ReviewEvent, REVIEW_PATTERN, LOCATION_PATTERN
    try:
        branches = json.loads(os.environ['BRANCH_NAMES_JSON'])
        if len(branches) != 4 or any(not LOCATION_PATTERN.fullmatch(k) for k in branches):
            raise ValueError('expected four verified resource mappings')
        client = GoogleClient()
        store = get_store()
        added = 0
        scanned = 0
        max_scan = min(200, max(1, int(os.getenv('MAX_BACKFILL_REVIEWS', '100'))))
        for location in branches:
            page = None
            while scanned < max_scan:
                response = client.list_reviews(location, page_token=page)
                for review in response.get('reviews', []):
                    if scanned >= max_scan:
                        break
                    name = str(review.get('name') or '')
                    if not REVIEW_PATTERN.fullmatch(name) or not name.startswith(location + '/reviews/'):
                        continue
                    scanned += 1
                    if store.enqueue(ReviewEvent(name, location, 'BACKFILL', 'manual-backfill')):
                        added += 1
                page = response.get('nextPageToken')
                if not page or scanned >= max_scan:
                    break
        return jsonify({'scanned':scanned,'queued_for_human_review':added,
                        'auto_publication':'disabled_for_backfill'}),200
    except (KeyError,ValueError,TypeError,RuntimeError) as exc:
        log.warning('Backfill blocked: %s',type(exc).__name__)
        return jsonify({'error':'configuration_or_storage_error'}),503
    except Exception as exc:
        log.warning('Backfill API error: %s',type(exc).__name__)
        return jsonify({'error':'provider_unavailable'}),502

@app.post('/internal/backfill-2026')
def backfill_2026_route():
    """Unanswered 2026 five-star reviews. Body: {"mode": "dry_run"|"canary"|"publish"}."""
    if not _internal_authorized(request):
        return jsonify({'error': 'unauthorized'}), 401
    import json
    import backfill_2026
    from google_client import GoogleAPIError
    body = request.get_json(silent=True) or {}
    mode = body.get('mode', 'dry_run') if isinstance(body, dict) else None
    if mode not in backfill_2026.MODES:
        return jsonify({'error': 'invalid_mode'}), 400
    is_canary = mode in ('canary', 'canary_preview')
    canary_review = body.get('review_name') if is_canary else None
    reply_text = body.get('reply_text') if is_canary else None
    if is_canary and not (isinstance(canary_review, str) and REVIEW_NAME_RE.fullmatch(canary_review)):
        return jsonify({'error': 'canary_requires_review_name'}), 400
    if is_canary and not isinstance(reply_text, str):
        return jsonify({'error': 'canary_requires_reply_text'}), 400
    try:
        branches = backfill_2026.validate_branches(json.loads(os.getenv('BRANCH_NAMES_JSON', '{}')))
        client = GoogleClient()
        if mode == 'dry_run':
            try:
                store = get_store()  # read-only ledger lookup
            except Exception:
                store = None
        else:
            store = get_store()
        result = backfill_2026.run(
            mode, client=client, store=store, branches=branches,
            process_one=process_one, env=os.environ, canary_review=canary_review, reply_text=reply_text,
            batch=min(10, max(1, int(os.getenv('MAX_DRAIN_BATCH', '5')))))
        if mode == 'dry_run' and store is None:
            result['ledger_by_branch'] = 'storage_unavailable'
        return jsonify(result), 200
    except backfill_2026.BackfillBlocked as exc:
        return jsonify({'error': 'publication_blocked', 'reason': str(exc), 'google_writes': 0}), 409
    except backfill_2026.BackfillIncomplete:
        return jsonify({'error': 'scan_incomplete', 'google_writes': 0}), 502
    except GoogleAPIError as err:
        return jsonify({'error': 'google_api_unavailable', 'provider_http': err.status,
                        'google_writes': 0}), 502
    except (KeyError, ValueError, TypeError, RuntimeError) as exc:
        log.warning('2026 backfill blocked: %s', type(exc).__name__)
        return jsonify({'error': 'configuration_or_storage_error', 'google_writes': 0}), 503


@app.post('/internal/canary-readback-only')
def verify_canary_readback_only():
    """ONE approved review: Google GET and conditional Neon reconciliation only.

    Does not call reply/PUT, drain, enqueue, AI or any publish path.
    Safe even with OWNER_EXPRESS_CONSENT=false after the single attempted PUT.
    """
    if not _internal_authorized(request):
        return jsonify({'error': 'unauthorized'}), 401
    body = request.get_json(silent=True)
    name = body.get('review_name') if isinstance(body, dict) else None
    allowed = os.getenv('BACKFILL_CANARY_REVIEW', '')
    if not isinstance(name, str) or not REVIEW_NAME_RE.fullmatch(name):
        return jsonify({'error': 'invalid_review_name', 'google_writes': 0}), 400
    if not allowed or name != allowed:
        return jsonify({'error': 'review_not_approved', 'google_writes': 0}), 403
    try:
        from reconcile_pending import reconcile_pending
        result = reconcile_pending(name, store=get_store(), google=GoogleClient())
        return jsonify({**result, 'review_name': name, 'google_writes': 0}), 200
    except Exception as exc:
        log.warning('Canary GET-only readback failed: %s', type(exc).__name__)
        return jsonify({'error': 'canary_readback_unavailable', 'google_writes': 0}), 502


@app.post('/internal/backfill-2026/report')
def backfill_2026_report():
    """Per-branch status counts of 2026 backfill jobs; 'posted' means confirmed by readback."""
    if not _internal_authorized(request):
        return jsonify({'error': 'unauthorized'}), 401
    import backfill_2026
    try:
        store = get_store()
        return jsonify({'by_branch': store.report_by_location(backfill_2026.EVENT_TYPE),
                        'confirmed_replies': store.verified_post_count(backfill_2026.EVENT_TYPE),
                        'google_reads': 0, 'google_writes': 0}), 200
    except Exception:
        return jsonify({'error': 'storage_unavailable'}), 503


# Optional isolated one-shot model probe; disabled unless staging-only run ID is set.
if os.getenv('AI_SMOKE_TEST_ID'):
    from staging_smoke import maybe_start_smoke
    maybe_start_smoke(get_store, SaudiReplyGenerator, log)


if __name__ == '__main__':
    app.run(port=8036)
