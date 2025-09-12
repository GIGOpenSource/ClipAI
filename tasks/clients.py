import requests
from requests_oauthlib import OAuth1


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
    API_BASE = 'https://api.x.com/2'

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
            # 统一使用 requests+OAuth1，避免与 tweepy 的内部属性不兼容
            if method == 'GET' and path == '/users/me':
                resp = requests.get(url, auth=self._oauth1, timeout=20)
            else:
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

    # List the accounts the given user follows (requires follows.read)
    def get_following(self, user_id: str, pagination_token: str | None = None, max_results: int = 100):
        params = []
        if max_results:
            params.append(f"max_results={max(1, min(1000, max_results))}")
        if pagination_token:
            params.append(f"pagination_token={pagination_token}")
        query = ('?' + '&'.join(params)) if params else ''
        return self._request('GET', f"/users/{user_id}/following{query}")

    # Follow a user (requires follows.write). In v2, endpoint:
    # POST /2/users/{source_user_id}/following { "target_user_id": "..." }
    def follow_user(self, source_user_id: str, target_user_id: str):
        payload = {"target_user_id": target_user_id}
        return self._request('POST', f"/users/{source_user_id}/following", payload)

    def get_user_by_username(self, username: str):
        # GET /2/users/by/username/:username
        uname = username.lstrip('@') if username else ''
        return self._request('GET', f"/users/by/username/{uname}")


class InstagramClient:
    GRAPH_BASE = 'https://graph.facebook.com'

    def __init__(self, api_version: str, page_access_token: str, ig_business_account_id: str):
        self.api_version = api_version or 'v19.0'
        self.page_access_token = page_access_token
        self.ig_business_account_id = ig_business_account_id

    def create_media(self, *, image_url: str | None = None, video_url: str | None = None, caption: str | None = None):
        """Create IG media container. Provide either image_url or video_url.
        Returns: { id: creation_id }
        """
        url = f"{self.GRAPH_BASE}/{self.api_version}/{self.ig_business_account_id}/media"
        data = {'access_token': self.page_access_token}
        if caption:
            data['caption'] = caption
        if image_url:
            data['image_url'] = image_url
        if video_url:
            data['video_url'] = video_url
        resp = requests.post(url, data=data, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def publish_media(self, creation_id: str):
        """Publish a previously created media container.
        Returns: { id: media_id }
        """
        url = f"{self.GRAPH_BASE}/{self.api_version}/{self.ig_business_account_id}/media_publish"
        resp = requests.post(url, data={'creation_id': creation_id, 'access_token': self.page_access_token}, timeout=20)
        resp.raise_for_status()
        return resp.json()


class ThreadsClient:
    GRAPH_BASE = 'https://graph.threads.net'

    def __init__(self, api_version: str, access_token: str, user_id: str):
        self.api_version = api_version or 'v1.0'
        self.access_token = access_token
        self.user_id = user_id

    def post_text(self, text: str):
        # Simplified Threads publish endpoint (subject to actual API capabilities)
        url = f"{self.GRAPH_BASE}/{self.api_version}/{self.user_id}/posts"
        resp = requests.post(url, data={'text': text, 'access_token': self.access_token}, timeout=20)
        resp.raise_for_status()
        return resp.json()
