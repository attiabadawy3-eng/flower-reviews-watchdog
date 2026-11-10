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

    def test_brand_and_rating_are_never_mentioned(self):
        p = reply_prompt(branch='فلور 1 الدمام', stars=5,
                         review_text='', previous_replies=[])
        self.assertIn('فلور فقط', p)
        self.assertIn('لا تذكر النجوم', p)
        self.assertEqual(validate_reply('حياك الله، شاكرين لك ثقتك في فلور ونتشرف فيك دائمًا.'),
                         'حياك الله، شاكرين لك ثقتك في فلور ونتشرف فيك دائمًا.')
        for bad in ('نشكرك على تقييمك بخمس نجوم ونورت فلور.',
                    'نشكرك على تقييمك 5 نجوم ونورت فلور.',
                    'نتشرف بخدمتك في شقق فلور الخليجية دائمًا.',
                    'نتشرف بخدمتك في فلور ⭐ وشاكرين لك.'):
            with self.subTest(reply=bad), self.assertRaises(ValueError):
                validate_reply(bad)

    def test_live_gemini_semantic_mistake_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_reply('حياك الله، نتشرف فيك ويسعدنا إننا قدمنا تجربة تنال إعراضك وترقى لرضاك.')

    def test_no_synthetic_sales_script(self):
        for draft in (
            'أهلًا وسهلًا، نتشرف بخدمتك ونسعى دايمًا لتقديم تجربة ترقى لرضاك.',
            'حياك الله، شاكرين ثقتك ونشكر الله أننا قدمنا تجربة تنال إعجابك.',
        ):
            with self.subTest(draft=draft), self.assertRaises(ValueError):
                validate_reply(draft)

    def test_unverified_complaint_facts_must_not_be_admitted(self):
        samples = (
            'نعتذر عن أي إزعاج تسببت فيه مشكلة التكييف وبطء الاستجابة.',
            'نعتذر عن المشكلة وقد تأخرنا في الاستجابة، ونتمنى تتواصل معنا.',
        )
        for text in samples:
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_reply(text)
        safe = ('حياك الله، نأسف إن تجربتك ما كانت بالمستوى المطلوب، '
                'ونتفهم ملاحظتك عن التكييف ونسعد بتواصلك مع الإدارة.')
        self.assertEqual(validate_reply(safe), safe)

    def test_generated_reply_must_not_mention_branch_number(self):
        for draft in (
            'حياك الله في فلور 1، ونشكرك على زيارتك الكريمة.',
            'نشكر لك تقييمك، ويسعدنا لقياك في فلور ٤ من جديد.',
        ):
            with self.subTest(draft=draft), self.assertRaises(ValueError):
                validate_reply(draft)

    def test_saudi_prompt_instructs_no_unnatural_phrases(self):
        p = reply_prompt(branch='فلور 2 السلام', stars=5,
                         review_text='المكان نظيف', previous_replies=[])
        self.assertIn('تنال إعراضك', p)
        self.assertIn('المصطنعة', p)

    def test_reply_validation(self):
        self.assertEqual(validate_reply('شكراً لك على تقييمك، ونسعد بخدمتك دائماً.'), 'شكراً لك على تقييمك، ونسعد بخدمتك دائماً.')
        with self.assertRaises(ValueError):
            validate_reply('شكراً')
        with self.assertRaises(ValueError):
            validate_reply('يسعدنا تواصلك على رقم 0501234567 بخصوص إقامتك.')

if __name__ == '__main__':
    unittest.main()


class TestRepetition(unittest.TestCase):
    RECENT = ['حياك الله، وشاكرين لك تقييمك وثقتك في فلور. يسعدنا إن إقامتك كانت طيبة ومرضية، '
              'ونتشرف بزيارتك القادمة لخدمتك بالشكل اللي يسعدك. أهلاً بك.']

    def test_stock_signoff_and_same_opening_rejected(self):
        from core import repetition_problem
        self.assertEqual(repetition_problem('يا هلا، شاكرين لك ثقتك وسعدنا بإقامتك. أهلاً بك.', []), 'stock sign-off')
        self.assertIsNotNone(repetition_problem('حياك الله، سعدنا بملاحظتك عن هدوء المكان.', self.RECENT))
        self.assertIsNotNone(repetition_problem(
            'حياك الله، وشاكرين لك تقييمك وثقتك في فلور. يسعدنا إن إقامتك كانت ممتازة ومريحة، ونتشرف بزيارتك القادمة.',
            self.RECENT))

    def test_varied_reply_accepted(self):
        from core import repetition_problem
        self.assertIsNone(repetition_problem('يا هلا، تسلم على كلامك الطيب عن نظافة الشقة، وهذا اللي نحرص عليه دايم.',
                                             self.RECENT))

    def test_prompt_lists_recent_replies_and_varies_openings(self):
        p = reply_prompt(branch='فلور 4', stars=5, review_text='', previous_replies=self.RECENT)
        self.assertIn(self.RECENT[0], p)
        self.assertIn('نوّع البداية', p)
        self.assertIn('أهلاً بك', p)          # named as a sign-off to avoid
        self.assertIn('بدون تعليق', p)

    def test_complaint_prompt_asks_for_empathy_without_admission(self):
        p = reply_prompt(branch='فلور 2', stars=2, review_text='المكيف خربان', previous_replies=[])
        self.assertIn('اعتذار مهذب', p)
        self.assertIn('دون الاعتراف', p)


class TestGeneratorRetries(unittest.TestCase):
    def make(self, outputs):
        import ai
        gen = ai.SaudiReplyGenerator.__new__(ai.SaudiReplyGenerator)
        seq = iter(outputs)
        prompts = []

        def fake(prompt):
            prompts.append(prompt)
            return next(seq)
        gen._generate = fake
        return gen, prompts

    def test_repeated_draft_is_rewritten(self):
        gen, prompts = self.make(['حياك الله، شاكرين لك ثقتك وسعدنا بإقامتك معنا. أهلاً بك.',
                                  'يا هلا، تسلم على كلامك الطيب، ويسعدنا إن الإقامة كانت مريحة لك.'])
        out = gen.make_reply(branch='فلور 1', stars=5, comment='', recent=[])
        self.assertTrue(out.startswith('يا هلا'))
        self.assertEqual(len(prompts), 2)
        self.assertIn('رُفضت', prompts[1])

    def test_fails_closed_after_three_repetitive_drafts(self):
        bad = 'حياك الله، شاكرين لك ثقتك وسعدنا بإقامتك معنا. أهلاً بك.'
        gen, _ = self.make([bad, bad, bad])
        with self.assertRaises(RuntimeError):
            gen.make_reply(branch='فلور 1', stars=5, comment='', recent=[])

    def test_rule_violation_is_retried(self):
        gen, _ = self.make(['شكرًا على الخمس نجوم يا غالي ونورتنا في فلور.',
                            'الله يحييك، سعدنا بثقتك ونتمنى نشوفك قريب في زيارة جاية.'])
        self.assertTrue(gen.make_reply(branch='فلور 3', stars=5, comment='', recent=[]).startswith('الله يحييك'))
