import unittest
from reply_quality import normalize, review_draft, select_safe_draft


class QualityGateTests(unittest.TestCase):
    def check(self, *, review, rating, reply, history=(), accepted=True):
        outcome = review_draft(review_text=review, rating=rating, reply=reply,
                               recent_replies=list(history))
        self.assertEqual(outcome.accepted, accepted, (reply, outcome.reasons))
        return outcome

    def test_realistic_scenarios(self):
        positive = [
            ("خالد ممتاز في الاستقبال", "يا هلا، أسعدنا كلامك عن خالد وحرصه على راحتك. نورت فلور ونتشرف بزيارتك الجاية."),
            ("الشقة نظيفة وهادئة", "حياك الله، سعدنا إن النظافة والهدوء كانوا على قد توقعاتك. نورت مكانك في فلور."),
            ("موقع جميل", "أهلًا وسهلًا، يهمنا إن موقعنا كان مناسب لك. تشرفنا باستضافتك ونتمنى نشوفك قريب."),
            ("خدمة الاستقبال ممتازة", "يا مرحبا، شهادتك في فريق الاستقبال تسعدنا كثير. حياك في فلور متى ما جيت."),
            ("الأسرة مريحة", "تشرفنا فيك، ونسعد لما تكون إقامتك مريحة. شكرًا لأنك شاركتنا تجربتك الجميلة."),
            ("كل شيء جميل", "يا هلا وسهلا، فرحنا برضاك عن زيارتك. نورتنا وننتظرك في زيارة ثانية على خير."),
        ]
        for review, reply in positive:
            with self.subTest(review=review):
                self.check(review=review, rating=5, reply=reply)
        negatives = [
            ("الموظفة أسلوبها سيئ", "نعتذر لك عن أسلوب التعامل اللي واجهته. ملاحظتك مهمة لنا ونأخذها بجدية، وشكرًا إنك وضحت تجربتك."),
            ("الغرفة ما كانت نظيفة", "نعتذر عن مستوى النظافة اللي وصفته. هذا مو الانطباع اللي نتمناه لضيوفنا ونقدّر صراحتك."),
            ("تأخر الدخول", "نعتذر عن تأخر إجراءات الدخول في زيارتك. نعرف قيمة وقتك ونقدّر إنك شاركتنا الملاحظة."),
            ("الإزعاج بالليل", "نأسف إن الإزعاج أثّر على راحتك وقت الإقامة. من حقك تنعم بالهدوء ونشكرك على تنبيهنا."),
            ("التكييف ما يبرد", "نعتذر لك عن تجربة التكييف غير المريحة. نشكرك على إيضاح المشكلة ونقدّر وقتك."),
            ("تعامل غير مناسب", "ملاحظتك عن التعامل وصلت لنا، ونعتذر عن التجربة. نتمنى تتاح لنا فرصة أفضل لاستضافتك."),
        ]
        for review, reply in negatives:
            with self.subTest(review=review):
                self.check(review=review, rating=1, reply=reply)
        neutral = [
            ("كانت الإقامة عادية", "نشكر مشاركتك لتجربتك. نقدر تقييمك ونتطلع لأن تكون زيارتك الجاية أجمل."),
            ("الموقع مناسب والغرفة صغيرة", "يا هلا، سعدنا إن الموقع ناسبك ونتفهم ملاحظتك عن مساحة الغرفة. شكرًا لوقتك."),
        ]
        for review, reply in neutral:
            with self.subTest(review=review):
                self.check(review=review, rating=3, reply=reply)
        empty = [
            "يا هلا والله، أسعدتنا نجومك وشرفت فلور. حياك الله في أي وقت.",
            "تشرفنا بتقييمك، وجودك يسعدنا ونتمنى نشوفك في فلور مرة ثانية.",
        ]
        for reply in empty:
            self.check(review="", rating=5, reply=reply)

    def test_exact_duplicate(self):
        x="يا مرحبا في فلور، نقدر كلامك الجميل عن فريقنا وتشرفنا بزيارتك."
        result=self.check(review="الفريق ممتاز",rating=5,reply=x,history=[x],accepted=False)
        self.assertIn("exact_duplicate_reply", result.reasons)

    def test_near_duplicate(self):
        first="يا هلا فيك، شكرًا لزيارتك الجميلة وثقتك في فريق فلور وننتظرك مرة ثانية بكل سرور."
        second="يا هلا فيك شكرًا لزيارتك الجميلة وثقتك بفريق فلور وننتظرك مرة ثانية بكل سرور."
        result=self.check(review="فريق ممتاز",rating=5,reply=second,history=[first],accepted=False)
        self.assertIn("near_duplicate_reply",result.reasons)

    def test_unverified_claim(self):
        result=self.check(review="تأخر الدخول",rating=1,reply="نعتذر لك عن التأخير. تم حل المشكلة بالكامل والموضوع انتهى.",accepted=False)
        self.assertIn("unverified_corrective_action_claim",result.reasons)

    def test_negative_no_emoji(self):
        result=self.check(review="الغرفة سيئة",rating=1,reply="نعتذر عن اللي صار معك، وملاحظتك تهمنا. ❤️",accepted=False)
        self.assertIn("emoji_in_negative_reply",result.reasons)

    def test_blank_review_no_fake_details(self):
        result=self.check(review="",rating=5,reply="يا هلا، يسعدنا أنك أعجبت بنظافة الغرفة وطاقم الاستقبال.",accepted=False)
        self.assertIn("specific_claim_without_review_text",result.reasons)

    def test_overused_opening(self):
        h=[f"يا هلا فيك، نقدر زيارتك الجميلة رقم {i} ونسعد بشوفتك." for i in range(4)]
        x="يا هلا فيك، شهادتك ترفع معنويات الفريق وننتظرك قريب في فلور."
        result=self.check(review="رائع",rating=5,reply=x,history=h,accepted=False)
        self.assertIn("overused_opening",result.reasons)

    def test_selection_no_posting(self):
        x="يا هلا والله، حياك الله في فلور. سعدنا بزيارتك الجميلة."
        y="أهلًا وسهلًا، فرحنا بكلامك عن تعاون الاستقبال. ونتطلع لزيارتك القادمة."
        got,decisions=select_safe_draft(review_text="الاستقبال متعاون",rating=5,candidates=[x,y],recent_replies=[x])
        self.assertEqual(got,y)
        self.assertFalse(decisions[0].accepted)
        self.assertTrue(decisions[1].accepted)

    def test_arabic_normalization(self):
        self.assertEqual(normalize('أهلاً وسَهْلاً'),normalize('اهلا وسهلا'))


if __name__ == '__main__':
    unittest.main()
