"""Only official Google Business Profile APIs are used here."""
import os
import requests
from core import REVIEW_PATTERN, LOCATION_PATTERN


class GoogleAPIError(Exception):
    def __init__(self, status: int, summary: str):
        self.status = status
        super().__init__(summary[:300])


class GoogleClient:
    def __init__(self):
        self.client_id = os.environ['GBP_CLIENT_ID']
        self.client_secret = os.environ['GBP_CLIENT_SECRET']
        self.refresh_token = os.environ['GBP_REFRESH_TOKEN']
        self.session = requests.Session()

    def access_token(self):
        resp = self.session.post('https://oauth2.googleapis.com/token',
                                 data={'client_id':self.client_id, 'client_secret':self.client_secret,
                                       'refresh_token':self.refresh_token,'grant_type':'refresh_token'},timeout=18)
        if resp.status_code != 200:
            raise GoogleAPIError(resp.status_code, 'OAuth refresh unsuccessful; do not rotate credentials automatically')
        return resp.json()['access_token']

    def request(self, method: str, resource: str, body=None):
        if not REVIEW_PATTERN.fullmatch(resource):
            raise ValueError('invalid review resource')
        path = f'https://mybusiness.googleapis.com/v4/{resource}' + ('/reply' if method == 'PUT' else '')
        resp = self.session.request(method,path,headers={'Authorization':f'Bearer {self.access_token()}'},json=body,timeout=20)
        if resp.status_code not in (200,201):
            # Don't log OAuth token, user content or the full provider payload.
            raise GoogleAPIError(resp.status_code, f'Google Reviews API returned HTTP {resp.status_code}')
        return resp.json()

    def list_reviews(self, location, page_token=None):
        """Explicit API recovery backfill. Never used to auto-post old reviews."""
        if not LOCATION_PATTERN.fullmatch(location):
            raise ValueError('invalid location resource')
        args = {'pageSize': 50}
        if page_token:
            args['pageToken'] = page_token
        response = self.session.get(
            f'https://mybusiness.googleapis.com/v4/{location}/reviews',
            headers={'Authorization': f'Bearer {self.access_token()}'},
            params=args, timeout=25)
        if response.status_code != 200:
            raise GoogleAPIError(response.status_code, f'Google Reviews list returned HTTP {response.status_code}')
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get('reviews', []), list):
            raise GoogleAPIError(502, 'Google Reviews list shape invalid')
        return data

    def get_review(self, resource):
        return self.request('GET',resource)

    def reply(self, resource, message):
        return self.request('PUT',resource,{'comment':message})

