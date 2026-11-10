"""Scheduled monitor: green ONLY when Google Reviews reads really succeed.

Service liveness (/live 200) is reported separately and never counts as
Google API success. Exit codes: 0 = reads verified on all four branches,
1 = Google API failing or response not proving success, 2 = monitor misconfigured.
"""
import json
import os
import sys


def evaluate(http_status, body):
    """Map a /internal/google-probe response to (exit_code, message)."""
    if not isinstance(body, dict):
        return 1, f'FAIL google_reviews_api: unreadable probe response (HTTP {http_status})'
    writes = body.get('google_writes')
    if writes is not None and not (type(writes) is int and writes == 0):
        return 1, 'FAIL probe reported Google writes or an invalid write count'
    # Success needs every proof field present with the exact type: an absent
    # google_writes, a string "0" or "4", or a boolean never counts as proof.
    if (http_status == 200 and body.get('status') == 'google_reads_verified' and
            type(body.get('branches_checked')) is int and body.get('branches_checked') == 4 and
            type(writes) is int and writes == 0):
        return 0, 'OK google_reviews_api: reads verified on 4/4 branches, zero writes'
    detail = body.get('status') or body.get('error') or 'unknown'
    provider = body.get('provider_http')
    suffix = f' provider_http={provider}' if provider is not None else ''
    return 1, f'FAIL google_reviews_api: {detail} (HTTP {http_status}){suffix}'


def main():
    import requests
    base = os.getenv('V6_BASE_URL', '').rstrip('/')
    secret = os.getenv('V6_CRON_SECRET', '')
    if not base or not secret:
        print('FAIL monitor not configured: V6_BASE_URL and V6_CRON_SECRET are required')
        return 2
    try:
        live = requests.get(base + '/live', timeout=90)
        print(f'INFO service_liveness: HTTP {live.status_code} (not evidence of Google API access)')
    except requests.RequestException as exc:
        print(f'INFO service_liveness: unreachable ({type(exc).__name__})')
    try:
        resp = requests.post(base + '/internal/google-probe',
                             headers={'Authorization': f'Bearer {secret}'}, timeout=120)
        try:
            body = resp.json()
        except ValueError:
            body = None
        code, message = evaluate(resp.status_code, body)
    except requests.RequestException as exc:
        code, message = 1, f'FAIL google_reviews_api: probe unreachable ({type(exc).__name__})'
    print(message)
    return code


if __name__ == '__main__':
    sys.exit(main())
