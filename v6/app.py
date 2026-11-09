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


def process_one(review_name=None):
    store = get_store()
    job = store.claim(review_name)
    if not job:
        return False
    import json
    from processor import process_claimed_job
    aliases = json.loads(os.getenv('BRANCH_NAMES_JSON','{}'))
    try:
        google_client = GoogleClient()
        ai_generator = SaudiReplyGenerator()
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
        minimum_stars=int(os.getenv('AUTO_REPLY_MIN_STARS','4')),
    )


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
    ready = bool(mapped and os.getenv('DATABASE_URL') and os.getenv('PUBSUB_AUDIENCE') and
                 os.getenv('PUBSUB_SERVICE_ACCOUNT_EMAIL') and os.getenv('GBP_REFRESH_TOKEN') and
                 os.getenv('GBP_CLIENT_ID') and os.getenv('GBP_CLIENT_SECRET') and os.getenv('GEMINI_API_KEY'))
    try:
        counts = get_store().counts()
        # Readiness here means configuration/storage only. It NEVER claims that
        # Google v4 Reviews is healthy; that needs a confirmed real API call.
        return jsonify({'status':'configured_api_unverified' if ready else 'configuration_incomplete',
                        'configured':ready,'google_reviews_api':'not_checked',
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
    get_store().prune_old()
    for _ in range(min(10,int(os.getenv('MAX_DRAIN_BATCH','5')))):
        if not process_one():
            break
        n+=1
    return jsonify({'processed':n,'jobs':get_store().counts()})


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

if __name__ == '__main__':
    app.run(port=8036)
