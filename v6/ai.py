"""Fail-closed Gemini adapter; no static/robotic fallback is posted."""
import os
import requests
from core import reply_prompt, validate_reply


class SaudiReplyGenerator:
    def __init__(self):
        self.api_key = os.environ['GEMINI_API_KEY']
        self.model = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
        self.session = requests.Session()

    def make_reply(self, *, branch: str, stars: int, comment: str, recent: list[str]) -> str:
        prompt = reply_prompt(branch=branch,stars=stars,review_text=comment,previous_replies=recent)
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent'
        response = self.session.post(url,headers={'x-goog-api-key': self.api_key},json={
            'contents':[{'parts':[{'text':prompt}]}],
            'generationConfig':{'temperature':0.75,'maxOutputTokens':450,'responseMimeType':'text/plain'},
        },timeout=25)
        if response.status_code != 200:
            raise RuntimeError(f'AI inference unavailable: HTTP {response.status_code}')
        data = response.json()
        candidates = data.get('candidates') or []
        if not candidates:
            raise RuntimeError('AI returned no safe candidate')
        parts = candidates[0].get('content',{}).get('parts',[])
        text = ''.join(p.get('text','') for p in parts if isinstance(p,dict))
        result = validate_reply(text)
        if result in recent:
            raise RuntimeError('duplicate AI reply')
        return result
