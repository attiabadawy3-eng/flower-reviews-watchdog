"""Fail-closed Gemini adapter; no static/robotic fallback is posted."""
import os
import requests
from core import reply_prompt, validate_reply, repetition_problem


class SaudiReplyGenerator:
    def __init__(self):
        self.api_key = os.environ['GEMINI_API_KEY']
        self.model = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
        self.session = requests.Session()

    def _generate(self, prompt: str) -> str:
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent'
        response = self.session.post(url,headers={'x-goog-api-key': self.api_key},json={
            'contents':[{'parts':[{'text':prompt}]}],
            'generationConfig':{'temperature':0.95,'topP':0.95,'maxOutputTokens':450,'responseMimeType':'text/plain'},
        },timeout=25)
        if response.status_code != 200:
            raise RuntimeError(f'AI inference unavailable: HTTP {response.status_code}')
        data = response.json()
        candidates = data.get('candidates') or []
        if not candidates:
            raise RuntimeError('AI returned no safe candidate')
        parts = candidates[0].get('content',{}).get('parts',[])
        return ''.join(p.get('text','') for p in parts if isinstance(p,dict))

    def make_reply(self, *, branch: str, stars: int, comment: str, recent: list[str]) -> str:
        """Up to three drafts; a draft that repeats recent replies is rewritten.

        Fails closed (raises) rather than posting a templated or repeated reply.
        """
        note = None
        for _ in range(3):
            prompt = reply_prompt(branch=branch, stars=stars, review_text=comment,
                                  previous_replies=recent, avoid_note=note)
            try:
                result = validate_reply(self._generate(prompt))
            except ValueError as exc:
                note = f'خالفت قاعدة: {exc}'
                continue
            problem = repetition_problem(result, recent)
            if problem is None and result not in recent:
                return result
            note = problem or 'مطابقة لرد سابق'
        raise RuntimeError('AI could not produce a non-repetitive reply')
