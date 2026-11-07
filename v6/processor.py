"""Review processing; never re-send a write with unconfirmed delivery."""
import logging
import datetime as dt
import os
from core import as_star_count, needs_owner_review
from google_client import GoogleAPIError

log = logging.getLogger('flower-v6.processor')


def process_claimed_job(*, job, store, google_client, ai_generator, branch_names,
                        auto_enabled=False, owner_consent=False, minimum_stars=4):
    review_name = job['review_name']
    pending_write = bool(job.get('verify_only'))
    armed = False
    try:
        if pending_write:
            # Once a PUT might have happened we must never call PUT again.
            review = google_client.get_review(review_name)
            current = ((review.get('reviewReply') or {}).get('comment') or '').strip()
            proposed = (job.get('reply_text') or '').strip()
            if current and proposed and current == proposed:
                store.finish(review_name, 'posted', reply_text=proposed)
            elif current:
                store.finish(review_name, 'existing', error='another owner reply was observed')
            elif job['attempts'] >= 3:
                store.finish(review_name, 'approval_required', error='write delivery uncertain; manual verification required')
            else:
                store.defer_verify(review_name, job['attempts'], 'reply not yet visible; verification only')
            return True

        review = google_client.get_review(review_name)
        if (review.get('reviewReply') or {}).get('comment'):
            store.finish(review_name, 'existing')
            return True
        comment = str(review.get('comment') or '')
        stars = as_star_count(review.get('starRating'))
        branch = branch_names.get(job['location_name'])
        if not branch or not 1 <= stars <= 5:
            store.finish(review_name, 'approval_required', error='unapproved branch mapping or missing rating')
            return True
        # A recovery/backfill must not auto-reply to stale or updated reviews.
        # Missing/invalid timestamps fail closed: the review stays for QA.
        allowed_age_h = max(1, int(os.getenv('AUTO_REPLY_MAX_AGE_HOURS', '72')))
        try:
            created = dt.datetime.fromisoformat(review['createTime'].replace('Z', '+00:00'))
            fresh = (created.tzinfo is not None and
                     dt.timedelta(0) <= dt.datetime.now(dt.timezone.utc) - created <=
                     dt.timedelta(hours=allowed_age_h))
        except (KeyError, ValueError, TypeError, AttributeError):
            fresh = False
        eligible = (fresh and job.get('event_type', 'NEW_REVIEW') == 'NEW_REVIEW' and
                    not needs_owner_review(stars, comment, minimum_stars) and
                    auto_enabled and owner_consent)
        reply = ai_generator.make_reply(branch=branch, stars=stars, comment=comment,
                                        recent=store.recent_replies())
        if not eligible:
            store.finish(review_name, 'approval_required', reply_text=reply)
            return True
        latest = google_client.get_review(review_name)
        if (latest.get('reviewReply') or {}).get('comment'):
            store.finish(review_name, 'existing')
            return True
        # Persist an immutable write intent BEFORE the external Google operation.
        store.mark_write_intent(review_name, reply)
        armed = True
        google_client.reply(review_name, reply)
        verified = google_client.get_review(review_name)
        if ((verified.get('reviewReply') or {}).get('comment') or '').strip() != reply:
            store.defer_verify(review_name, job['attempts'], 'reply not confirmed after PUT')
            return False
        store.finish(review_name, 'posted', reply_text=reply)
        return True
    except (GoogleAPIError, RuntimeError, ValueError, KeyError, OSError) as exc:
        if armed or pending_write:
            store.defer_verify(review_name, job['attempts'], f'{type(exc).__name__}: verify only')
        else:
            store.retry(review_name, job['attempts'], f'{type(exc).__name__}: {exc}')
        log.warning('Review processing deferred; kind=%s', type(exc).__name__)
        return False
