import base64
import json
import unittest
from core import parse_pubsub, InvalidNotification, as_star_count, needs_owner_review, reply_prompt, validate_reply


def wrap(data, id='msg-123'):
    return {'message': {'messageId': id, 'data': base64.b64encode(json.dumps(data).encode()).decode()}}


class TestCore(unittest.TestCase):
    def test_camel_case_notification(self):
        e = parse_pubsub(wrap({'type': 'NEW_REVIEW', 'reviewName': 'accounts/12/locations/34/reviews/r1', 'locationName': 'accounts/12/locations/34'}))
        self.assertEqual(e.review_name, 'accounts/12/locations/34/reviews/r1')
        self.assertEqual(e.message_id, 'msg-123')

    def test_real_world_naming(self):
        e = parse_pubsub(wrap({'type': 'NEW_REVIEW', 'review': 'accounts/12/locations/34/reviews/r2', 'location': 'accounts/12/locations/34'}))
        self.assertEqual(e.location_name, 'accounts/12/locations/34')

    def test_v1_location_alias_uses_verified_mapping(self):
        e = parse_pubsub(wrap({'type':'NEW_REVIEW','review':'locations/34/reviews/r8','location':'locations/34'}),
                         location_aliases={'locations/34':'accounts/12/locations/34'})
        self.assertEqual(e.review_name, 'accounts/12/locations/34/reviews/r8')

    def test_unmapped_location_fails_closed(self):
        with self.assertRaises(InvalidNotification):
            parse_pubsub(wrap({'type':'NEW_REVIEW','review':'locations/34/reviews/r8','location':'locations/34'}))

    def test_missing_location_inferred_from_full_review_name(self):
        e = parse_pubsub(wrap({'type': 'UPDATED_REVIEW', 'review_name': 'accounts/12/locations/34/reviews/r3'}))
        self.assertEqual(e.location_name, 'accounts/12/locations/34')

    def test_ignores_other_notifications(self):
        self.assertIsNone(parse_pubsub(wrap({'type': 'GOOGLE_UPDATE'})))

    def test_rejects_mismatched_location(self):
        with self.assertRaises(InvalidNotification):
            parse_pubsub(wrap({'type': 'NEW_REVIEW','review': 'accounts/12/locations/34/reviews/r', 'location': 'accounts/12/locations/99'}))

    def test_rejects_malformed_encoded(self):
        with self.assertRaises(InvalidNotification):
            parse_pubsub({'message': {'data': '%%'}})

    def test_rejects_non_object_pubsub_envelope(self):
        with self.assertRaises(InvalidNotification):
            parse_pubsub([{'message': {'data': 'test'}}])

    def test_rejects_base64_decoded_non_utf8(self):
        encoded = base64.b64encode(b'\xff').decode()
        with self.assertRaises(InvalidNotification):
            parse_pubsub({'message': {'data': encoded}})

    def test_rating_conversion(self):
        self.assertEqual(as_star_count('FIVE'), 5)
        self.assertEqual(as_star_count('THREE'), 3)
        self.assertEqual(as_star_count('INVALID'), 0)

    def test_high_risk_gate(self):
        self.assertTrue(needs_owner_review(5, 'سرقة أغراض من الغرفة', 4))
        self.assertTrue(needs_owner_review(2, 'إزعاج', 4))
        self.assertFalse(needs_owner_review(5, 'مكان ممتاز', 4))

    def test_prompt_says_no_false_claims_and_saudi(self):
        x = reply_prompt(branch='فلور 1 الدمام', stars=5, review_text='النظافة ممتازة', previous_replies=[])
        self.assertIn('سعودي', x)
        self.assertIn('لا تعد باسترجاع', x)
        self.assertIn('النظافة ممتازة', x)

    def test_reply_validation(self):
        self.assertEqual(validate_reply('شكراً لك على تقييمك، ونسعد بخدمتك دائماً.'), 'شكراً لك على تقييمك، ونسعد بخدمتك دائماً.')
        with self.assertRaises(ValueError):
            validate_reply('شكراً')
        with self.assertRaises(ValueError):
            validate_reply('يسعدنا تواصلك على رقم 0501234567 بخصوص إقامتك.')

if __name__ == '__main__':
    unittest.main()
