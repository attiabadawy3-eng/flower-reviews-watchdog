"""Opt-in one-review pilot: default is GET-only, never enables batch auto reply.

This utility is for a supervised local pilot, not the ongoing cloud worker.
Do not copy Google OAuth token files to GitHub or Render.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from core import REVIEW_PATTERN, LOCATION_PATTERN, ReviewEvent, validate_reply
from google_client import GoogleClient
from storage import Store
from processor import process_claimed_job, reply_matches_approved


class ApprovedTextGenerator:
    def __init__(self, approved_text):
        self.approved_text = approved_text

    def make_reply(self, **kwargs):
        return self.approved_text


def perform_pilot(review_name, reply_text, *, publish=False, google=None, store=None):
    """Never issues PUT unless a single review and approved text hash match.

    If a review already has a reply or appears in the durable ledger, no PUT
    is attempted. Even after a timeout, the processor verifies only.
    """
    if not REVIEW_PATTERN.fullmatch(review_name):
        raise ValueError('invalid review resource')
    text = validate_reply(reply_text)
    client = google if google is not None else GoogleClient()
    live = client.get_review(review_name)
    if live.get('name') != review_name:
        raise RuntimeError('Google review identity mismatch')
    if ((live.get('reviewReply') or {}).get('comment') or '').strip():
        return {'status': 'already_replied', 'write_attempted': False}
    if not publish:
        return {'status': 'dry_run_no_write', 'write_attempted': False}

    expected_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    if (os.getenv('OWNER_EXPRESS_CONSENT') != 'true' or
            os.getenv('OWNER_APPROVED_REVIEW_NAME') != review_name or
            os.getenv('OWNER_APPROVED_REPLY_SHA256') != expected_hash):
        raise PermissionError('exact owner approval required for one review and reply')
    location = review_name.rsplit('/reviews/', 1)[0]
    if not LOCATION_PATTERN.fullmatch(location):
        raise ValueError('invalid review location')
    branches = json.loads(os.getenv('BRANCH_NAMES_JSON', '{}'))
    if len(branches) != 4 or location not in branches or not branches[location]:
        raise ValueError('four-branch verified mapping required')

    durable_store = store if store is not None else Store()
    event = ReviewEvent(review_name, location, 'NEW_REVIEW', 'owner-approved-one-shot')
    if not durable_store.enqueue(event):
        return {'status': 'already_in_durable_ledger', 'write_attempted': False}
    job = durable_store.claim(review_name)
    if not job:
        return {'status': 'claim_not_acquired', 'write_attempted': False}
    result = process_claimed_job(
        job=job, store=durable_store, google_client=client,
        ai_generator=ApprovedTextGenerator(text),
        branch_names=branches, auto_enabled=True, owner_consent=True,
        minimum_stars=5,
    )
    # A true result can also mean approval_required or another existing reply.
    # Never report "posted" merely because the processor returned True.
    confirmed = False
    try:
        latest = client.get_review(review_name)
        confirmed = reply_matches_approved((latest.get('reviewReply') or {}).get('comment'), text)
    except Exception:
        pass
    return {'status': 'posted_readback_confirmed' if result and confirmed
            else 'not_confirmed_check_ledger', 'write_attempted': True}


def main():
    p = argparse.ArgumentParser(description='FLOWER V6 single-review controlled pilot')
    p.add_argument('--review-name', required=True)
    p.add_argument('--reply-file', required=True)
    p.add_argument('--publish', action='store_true',
                   help='Requires exact approval environment and durable DB')
    args = p.parse_args()
    reply = Path(args.reply_file).read_text(encoding='utf-8').strip()
    print(json.dumps(perform_pilot(args.review_name, reply, publish=args.publish)))


if __name__ == '__main__':
    main()
