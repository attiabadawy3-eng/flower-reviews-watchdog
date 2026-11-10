import unittest
from watchdog_checks import check_scan, evaluate_probe, main

class ScanTests(unittest.TestCase):
    def test_outages_fail_closed(self):
        bad = [
            {'ok': True, 'seen': 0, 'errors': 4},
            {'ok': True, 'seen': 0, 'errors': 0},
            {'ok': True, 'seen': 120, 'errors': 1},
            {'ok': False, 'error': 'Google API GET 404'},
            {'ok': True, 'seen': 200},
            {'ok': True, 'seen': 200, 'errors': -1},
            {'ok': True, 'seen': -2, 'errors': 0},
            {'ok': True, 'seen': 200, 'errors': False},
            {'ok': True, 'seen': '200', 'errors': 0},
            {'ok': True, 'seen': 200, 'errors': 0.0},
            None, []
        ]
        for body in bad:
            with self.subTest(body=body):
                self.assertEqual(check_scan(body)[0], 1)

    def test_valid_scan_passes(self):
        self.assertEqual(check_scan({'ok': True, 'seen': 200, 'errors': 0})[0], 0)

    def test_cli_bad_json_is_red(self):
        self.assertEqual(main(['script', 'scan', 'invalid']), 1)

class ProbeTests(unittest.TestCase):
    def test_proof_fields_exact(self):
        valid = {'status': 'google_reads_verified', 'branches_checked': 4, 'google_writes': 0}
        self.assertEqual(evaluate_probe(200, valid)[0], 0)
        for modified in (
            {'google_writes': None}, {'google_writes': '0'}, {'google_writes': False},
            {'google_writes': 1}, {'branches_checked': '4'},
            {'branches_checked': True}, {'branches_checked': 3}
        ):
            self.assertEqual(evaluate_probe(200, dict(valid, **modified))[0], 1)
        self.assertEqual(evaluate_probe(502, valid)[0], 1)
        self.assertEqual(evaluate_probe(200, {'status': 'alive'})[0], 1)

if __name__ == '__main__':
    unittest.main()
