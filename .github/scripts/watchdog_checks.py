"""Read-only checks for FLOWER reviews. Liveness is not API readiness."""
import json
import os
import sys

def check_scan(d):
    if not isinstance(d, dict):
        return 1, 'FAIL scan: response is not a JSON object'
    summary = 'seen={} candidates={} posted={} held={} errors={}'.format(
        d.get('seen', 0), d.get('candidates', 0), d.get('posted', 0),
        d.get('held', 0), d.get('errors', 0))
    if d.get('ok') is not True:
        return 1, 'FAIL scan: ok is not true; ' + summary
    errors, seen = d.get('errors'), d.get('seen')
    if type(errors) is not int or type(seen) is not int or errors < 0 or seen < 0:
        return 1, 'FAIL scan: missing/invalid counters; ' + summary
    if errors > 0:
        return 1, 'FAIL scan: Google Reviews API errors; ' + summary
    if seen == 0:
        return 1, 'FAIL scan: zero reviews read across all branches; ' + summary
    return 0, 'OK scan: ' + summary

def evaluate_probe(http_status, body):
    if not isinstance(body, dict):
        return 1, f'FAIL google_reviews_api: unreadable probe response (HTTP {http_status})'
    writes = body.get('google_writes')
    if writes is not None and not (type(writes) is int and writes == 0):
        return 1, 'FAIL probe reported Google writes or invalid write count'
    if (http_status == 200 and body.get('status') == 'google_reads_verified'
        and type(body.get('branches_checked')) is int
        and body.get('branches_checked') == 4
        and type(writes) is int and writes == 0):
        return 0, 'OK google_reviews_api: reads verified on 4/4 branches, zero writes'
    detail = body.get('status') or body.get('error') or 'unknown'
    return 1, f'FAIL google_reviews_api: {detail} (HTTP {http_status})'

def main(argv):
    if len(argv) >= 2 and argv[1] == 'scan':
        try:
            data = json.loads(argv[2] if len(argv) > 2 else '')
        except ValueError:
            data = None
        code, msg = check_scan(data)
    else:
        code, msg = 2, 'usage: watchdog_checks.py scan <json>'
    print(('::error::' if code else '') + msg)
    return code

if __name__ == '__main__':
    sys.exit(main(sys.argv))
