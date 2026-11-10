import unittest
import datetime as dt
from processor import process_claimed_job
from google_client import GoogleAPIError

RESOURCE='accounts/12/locations/34/reviews/r1'
LOCATION='accounts/12/locations/34'


class FakeStore:
    def __init__(self):
        self.finished=[];self.retried=[];self.deferred=[];self.intent=[]
    def finish(self,*args,**kwargs): self.finished.append((args,kwargs))
    def retry(self,*args): self.retried.append(args)
    def recent_replies(self): return []
    def mark_write_intent(self,*args): self.intent.append(args)
    def defer_verify(self,*args): self.deferred.append(args)


class FakeGoogle:
    def __init__(self,mode='ok'):
        self.mode=mode;self.calls=[];self.existing=''
    def get_review(self,resource):
        self.calls.append('GET')
        if self.mode=='blocked': raise GoogleAPIError(404,'Method not found')
        return {'starRating':'FIVE','comment':'نظافة ممتازة',
                'createTime':dt.datetime.now(dt.timezone.utc).isoformat(),
                'reviewReply':{'comment':self.existing} if self.existing else {}}
    def reply(self,resource,text):
        self.calls.append('PUT')
        if self.mode!='not_confirmed':self.existing=text
        if self.mode=='timeout_after_write': raise GoogleAPIError(504,'Gateway timeout after commit')
        return {}


class FakeAI:
    def make_reply(self,**kwargs):
        return 'الله يسعدك على كلامك الجميل، ونسعد جدًا إن النظافة نالت رضاك. حياك الله دوم.'


class ProcessorTests(unittest.TestCase):
    def go(self,store=None,google=None,auto=True,consent=True,minimum=4):
        s=store or FakeStore(); g=google or FakeGoogle()
        ok=process_claimed_job(job={'review_name':RESOURCE,'location_name':LOCATION,'attempts':1,'event_type':'NEW_REVIEW'},
            store=s,google_client=g,ai_generator=FakeAI(),branch_names={LOCATION:'فلور 1 العنود'},
            auto_enabled=auto,owner_consent=consent,minimum_stars=minimum)
        return ok,s,g

    def test_posts_verified_reply_once(self):
        ok,s,g=self.go()
        self.assertTrue(ok)
        self.assertEqual(g.calls,['GET','GET','PUT','GET'])
        self.assertEqual(s.finished[0][0][1],'posted')
        self.assertEqual(len(s.intent),1)

    def test_404_fails_closed(self):
        ok,s,g=self.go(google=FakeGoogle('blocked'))
        self.assertFalse(ok);self.assertEqual(g.calls,['GET']);self.assertFalse(s.finished)
        self.assertEqual(len(s.retried),1)

    def test_existing_reply_untouched(self):
        g=FakeGoogle();g.existing='Already replied by staff'
        ok,s,g=self.go(google=g)
        self.assertTrue(ok);self.assertEqual(g.calls,['GET'])
        self.assertEqual(s.finished[0][0][1],'existing')

    def test_no_express_consent_means_no_post(self):
        ok,s,g=self.go(consent=False)
        self.assertTrue(ok);self.assertEqual(g.calls,['GET'])
        self.assertEqual(s.finished[0][0][1],'approval_required')

    def test_no_auto_enable_means_no_post(self):
        ok,s,g=self.go(auto=False)
        self.assertTrue(ok);self.assertEqual(g.calls,['GET'])
        self.assertEqual(s.finished[0][0][1],'approval_required')

    def test_put_needs_readback_confirmation(self):
        ok,s,g=self.go(google=FakeGoogle('not_confirmed'))
        self.assertFalse(ok);self.assertEqual(g.calls,['GET','GET','PUT','GET'])
        self.assertFalse(s.finished);self.assertEqual(len(s.deferred),1);self.assertFalse(s.retried)

    def test_timeout_after_put_is_verify_only_and_never_puts_again(self):
        google=FakeGoogle('timeout_after_write')
        ok,store,_=self.go(google=google)
        self.assertFalse(ok)
        self.assertEqual(google.calls,['GET','GET','PUT'])
        self.assertEqual(len(store.intent),1)
        self.assertEqual(len(store.deferred),1)
        self.assertFalse(store.retried)
        result=process_claimed_job(job={'review_name':RESOURCE,'location_name':LOCATION,
                                         'attempts':2,'verify_only':True,
                                         'reply_text':store.intent[0][1]},
            store=store,google_client=google,ai_generator=FakeAI(),
            branch_names={LOCATION:'فلور 1 العنود'},auto_enabled=True,owner_consent=True)
        self.assertTrue(result)
        self.assertEqual(google.calls,['GET','GET','PUT','GET'])
        self.assertEqual(store.finished[-1][0][1],'posted')

    def test_updated_review_is_never_auto_posted(self):
        store=FakeStore(); google=FakeGoogle()
        ok=process_claimed_job(job={'review_name':RESOURCE,'location_name':LOCATION,
                                   'attempts':1,'event_type':'UPDATED_REVIEW'},
            store=store,google_client=google,ai_generator=FakeAI(),
            branch_names={LOCATION:'فلور 1 العنود'},auto_enabled=True,owner_consent=True)
        self.assertTrue(ok)
        self.assertNotIn('PUT',google.calls)
        self.assertEqual(store.finished[0][0][1],'approval_required')

    def test_missing_created_timestamp_requires_approval(self):
        class MissingDateGoogle(FakeGoogle):
            def get_review(self,r):
                x=super().get_review(r);x.pop('createTime',None);return x
        ok,store,google=self.go(google=MissingDateGoogle())
        self.assertTrue(ok)
        self.assertNotIn('PUT',google.calls)
        self.assertEqual(store.finished[0][0][1],'approval_required')

    def test_stale_review_never_auto_posted(self):
        class OldDateGoogle(FakeGoogle):
            def get_review(self,r):
                x=super().get_review(r)
                x['createTime']=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=4)).isoformat()
                return x
        ok,store,google=self.go(google=OldDateGoogle())
        self.assertTrue(ok)
        self.assertNotIn('PUT',google.calls)
        self.assertEqual(store.finished[0][0][1],'approval_required')

    def test_unconfirmed_write_never_reissues_put(self):
        google=FakeGoogle('not_confirmed')
        ok,store,_=self.go(google=google)
        self.assertFalse(ok)
        reply=store.intent[0][1]
        ok=process_claimed_job(job={'review_name':RESOURCE,'location_name':LOCATION,
                                    'attempts':3,'verify_only':True,'reply_text':reply},
            store=store,google_client=google,ai_generator=FakeAI(),
            branch_names={LOCATION:'فلور 1 العنود'},auto_enabled=True,owner_consent=True)
        self.assertTrue(ok)
        self.assertEqual(google.calls.count('PUT'),1)
        self.assertEqual(store.finished[-1][0][1],'approval_required')


    def test_pending_write_google_translation_is_posted_without_new_put(self):
        from processor import reply_matches_approved
        original = 'حياك الله، شاكرين لك ثقتك في فلور ونتشرف فيك دائمًا.'
        self.assertTrue(reply_matches_approved(original, original))
        self.assertTrue(reply_matches_approved(original + '\n\n(Translated by Google) Welcome! Thank you for your visit.', original))
        self.assertFalse(reply_matches_approved(original + '\n\n(Translated by Google)', original))
        self.assertFalse(reply_matches_approved(original + ' Extra\n\n(Translated by Google) Welcome!', original))
        g = FakeGoogle()
        g.existing = original + '\n\n(Translated by Google) Welcome! Thank you for your visit.'
        s = FakeStore()
        ok = process_claimed_job(
            job={'review_name': RESOURCE, 'location_name': LOCATION, 'attempts': 2,
                 'verify_only': True, 'reply_text': original},
            store=s, google_client=g, ai_generator=FakeAI(),
            branch_names={LOCATION: 'فلور 1 العنود'},
            auto_enabled=False, owner_consent=False)
        self.assertTrue(ok)
        self.assertEqual(g.calls, ['GET'])
        self.assertEqual(s.finished[0][0][1], 'posted')
        self.assertFalse(s.deferred)
        self.assertFalse(s.intent)

    def test_wrong_reply_with_translation_is_not_claimed_as_ours(self):
        g = FakeGoogle()
        original = 'حياك الله، شاكرين لك ثقتك في فلور ونتشرف فيك دائمًا.'
        g.existing = original + ' تعديل مختلف\n\n(Translated by Google) Welcome!'
        s = FakeStore()
        ok = process_claimed_job(
            job={'review_name': RESOURCE, 'location_name': LOCATION, 'attempts': 2,
                 'verify_only': True, 'reply_text': original},
            store=s, google_client=g, ai_generator=FakeAI(),
            branch_names={LOCATION: 'فلور 1 العنود'},
            auto_enabled=False, owner_consent=False)
        self.assertTrue(ok)
        self.assertEqual(g.calls, ['GET'])
        self.assertEqual(s.finished[0][0][1], 'existing')
        self.assertFalse(s.intent)

    def test_post_write_readback_allows_google_translation(self):
        class TranslatedGoogle(FakeGoogle):
            def get_review(self, name):
                data = super().get_review(name)
                if self.existing:
                    data['reviewReply'] = {
                        'comment': self.existing + '\n\n(Translated by Google) Thanks for visiting.'
                    }
                return data
        ok, store, google = self.go(google=TranslatedGoogle())
        self.assertTrue(ok)
        self.assertEqual(google.calls, ['GET', 'GET', 'PUT', 'GET'])
        self.assertEqual(store.finished[0][0][1], 'posted')
        self.assertFalse(store.deferred)

if __name__ == '__main__':
    unittest.main()
