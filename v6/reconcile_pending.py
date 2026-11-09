"""Reconcile ONE pending Google reply via GET only, with no Google write path.

Requires existing durable Store and its original approved reply_text.
Safe for a previously sent PUT whose readback appeared later or was translated.
"""
import argparse
import json
import time

from core import REVIEW_PATTERN
from google_client import GoogleClient
from processor import reply_matches_approved
from storage import Store


def reconcile_pending(review_name, *, store=None, google=None):
    if not REVIEW_PATTERN.fullmatch(review_name):
        raise ValueError('invalid Google review identifier')
    ledger = store if store is not None else Store()
    with ledger.connection() as db:
        row = db.execute(
            ledger._sql('SELECT status,reply_text FROM review_jobs WHERE review_name=%s'),
            (review_name,),
        ).fetchone()
    if not row:
        return {'status': 'ledger_entry_not_found', 'google_write_attempted': False}
    status, approved = row
    if status != 'verify_pending' or not approved:
        return {'status': 'not_pending_verification', 'google_write_attempted': False}

    client = google if google is not None else GoogleClient()
    review = client.get_review(review_name)  # No PUT methods are referenced.
    if review.get('name') != review_name:
        raise RuntimeError('Google review identity mismatch')
    reply = review.get('reviewReply') or {}
    observed = str(reply.get('comment') or '')
    if not observed.strip():
        return {'status': 'awaiting_google_visibility', 'google_write_attempted': False}
    moderation = reply.get('reviewReplyState')
    if moderation == 'REJECTED':
        return {'status': 'google_reply_rejected', 'google_write_attempted': False}
    if moderation == 'PENDING':
        return {'status': 'google_moderation_pending', 'google_write_attempted': False}
    if not reply_matches_approved(observed, approved):
        return {'status': 'manual_review_text_mismatch', 'google_write_attempted': False}

    # Compare-and-swap: never overwrite a concurrent change to the approved
    # text or a ledger status transition.
    with ledger.connection() as db:
        result = db.execute(ledger._sql(
            "UPDATE review_jobs SET status='posted',last_error='',lease_until=0,"
            "updated_at=%s WHERE review_name=%s AND status='verify_pending' "
            "AND reply_text=%s"
        ), (time.time(), review_name, approved))
    return {
        'status': 'posted_readback_confirmed' if result.rowcount == 1
        else 'ledger_changed_during_verification',
        'google_write_attempted': False,
    }


def main():
    parser = argparse.ArgumentParser(description='Get-only confirmation of one pending review reply')
    parser.add_argument('--review-name', required=True)
    args = parser.parse_args()
    print(json.dumps(reconcile_pending(args.review_name)))


if __name__ == '__main__':
    main()
