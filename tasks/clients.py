import requests
from requests_oauthlib import OAuth1
import tweepy


class FacebookClient:
    GRAPH_BASE = 'https://graph.facebook.com'

    def __init__(self, api_version: str, page_access_token: str, page_id: str):
        self.api_version = api_version or 'v19.0'
        self.page_access_token = page_access_token
        self.page_id = page_id

    def post_feed(self, message: str):
        url = f"{self.GRAPH_BASE}/{self.api_version}/{self.page_id}/feed"
        resp = requests.post(url, data={'message': message, 'access_token': self.page_access_token}, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def reply_comment(self, comment_id: str, message: str):
        url = f"{self.GRAPH_BASE}/{self.api_version}/{comment_id}/comments"
        resp = requests.post(url, data={'message': message, 'access_token': self.page_access_token}, timeout=15)
        resp.raise_for_status()
        return resp.json()


class TwitterClient:
    API_BASE = 'https://api.twitter.com/2'

    def __init__(
        self,
        bearer_token: str | None = None,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        access_token: str | None = None,
        access_token_secret: str | None = None,
    ):
        # 优先使用 OAuth2 用户上下文/应用上下文（若提供 bearer_token）
        self.bearer_token = bearer_token
        self._oauth1 = None
        if not self.bearer_token and consumer_key and consumer_secret and access_token and access_token_secret:
            # 仅在没有 OAuth2 token 时才启用 OAuth1 会话，避免误把 OAuth2 refresh_token 当 secret
            self._oauth1 = OAuth1(consumer_key, consumer_secret, access_token, access_token_secret)

    def _headers(self):
        hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.bearer_token:
            hdrs["Authorization"] = f"Bearer {self.bearer_token}"
        return hdrs

    def _request(self, method: str, path: str, json_payload: dict | None = None):
        url = f"{self.API_BASE}{path}"
        if not self._oauth1 and method in {'POST','DELETE'} and path.startswith('/tweets'):
            # Free 计划下不支持写入；保底使用 Bearer 仅返回 403，由上层处理
            resp = requests.request(method, url, json=json_payload, headers=self._headers(), timeout=20)
        elif self._oauth1:
            # 对于只读接口优先用官方 SDK（tweepy）
            if method == 'GET' and path == '/users/me':
                # tweepy.Client with OAuth1 user keys
                # tweepy 4.x: Client(consumer_key=..., consumer_secret=..., access_token=..., access_token_secret=...)
                client = tweepy.Client(consumer_key=self._oauth1.client.client_key,
                                       consumer_secret=self._oauth1.client.client_secret,
                                       access_token=self._oauth1.resource_owner_key,
                                       access_token_secret=self._oauth1.resource_owner_secret)
                me = client.get_me(user_auth=True)
                return me.data.data if hasattr(me, 'data') and hasattr(me.data, 'data') else (me.data or {})
            # 其他读接口暂用 requests+OAuth1
            resp = requests.request(method, url, json=json_payload, auth=self._oauth1, timeout=20)
        else:
            resp = requests.request(method, url, json=json_payload, headers=self._headers(), timeout=20)
        resp.raise_for_status()
        return resp.json()

    def _extract_rate_limit(self, response: requests.Response) -> dict:
        headers = response.headers or {}
        rl = {
            'x-rate-limit-limit': headers.get('x-rate-limit-limit'),
            'x-rate-limit-remaining': headers.get('x-rate-limit-remaining'),
            'x-rate-limit-reset': headers.get('x-rate-limit-reset'),
        }
        try:
            if rl['x-rate-limit-remaining'] is not None:
                remaining = int(rl['x-rate-limit-remaining'])
                rl['warning'] = remaining <= 3
            else:
                rl['warning'] = False
        except Exception:
            rl['warning'] = False
        return rl

    def get_me_with_headers(self):
        """同 get_me，但返回 (data, rate_limit)"""
        if self._oauth1:
            # 回退到 OAuth1 直接请求，获取 headers
            url = f"{self.API_BASE}/users/me"
            resp = requests.get(url, auth=self._oauth1, timeout=20)
            resp.raise_for_status()
            return resp.json(), self._extract_rate_limit(resp)
        # OAuth2 bearer
        url = f"{self.API_BASE}/users/me"
        resp = requests.get(url, headers=self._headers(), timeout=20)
        resp.raise_for_status()
        return resp.json(), self._extract_rate_limit(resp)

    # Read-only: get current user (OAuth1/OAuth2 user context)
    def get_me(self):
        return self._request('GET', '/users/me')

    def post_tweet(self, text: str):
        return self._request('POST', '/tweets', {'text': text})

    def reply_tweet(self, reply_to_tweet_id: str, text: str):
        payload = {'text': text, 'reply': {'in_reply_to_tweet_id': reply_to_tweet_id}}
        return self._request('POST', '/tweets', payload)


class InstagramClient:
    GRAPH_BASE = 'https://graph.facebook.com'

    def __init__(self, api_version: str, page_access_token: str, ig_business_account_id: str):
        self.api_version = api_version or 'v19.0'
        self.page_access_token = page_access_token
        self.ig_business_account_id = ig_business_account_id

    def post_media(self, caption: str):
        # Simplified creation container (no media upload here)
        url = f"{self.GRAPH_BASE}/{self.api_version}/{self.ig_business_account_id}/media"
        resp = requests.post(url, data={'caption': caption, 'access_token': self.page_access_token}, timeout=15)
        resp.raise_for_status()
        return resp.json()

