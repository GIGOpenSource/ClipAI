from typing import Dict, Any
import time
from django.conf import settings
import urllib.parse
from keywords.models import KeywordConfig
from ..clients import TwitterClient
from ..models import SocialPost
from django.core.cache import cache


def _block_key(oid, prov, aid):
    return f"rl:block:{oid or 0}:{prov}:{aid or 0}"


def _is_blocked(oid, prov, aid) -> bool:
    return bool(cache.get(_block_key(oid, prov, aid)))


def _block_for(oid, prov, aid, seconds: int):
    if seconds and seconds > 0:
        cache.set(_block_key(oid, prov, aid), 1, timeout=seconds)


def handle(task, social_cfg, account, text_to_post: str, response: Dict[str, Any],
           idem_guard, rate_guard):
    consumer_key = getattr(social_cfg, 'client_id', '') or None
    consumer_secret = getattr(social_cfg, 'client_secret', '') or None
    bearer_user = None
    if account and account.get_access_token() and ('tweet.' in ' '.join(account.scopes or []) or (account.scopes == [])):
        bearer_user = account.get_access_token()
    has_oauth1 = bool(account and account.get_access_token() and account.get_refresh_token())
    bearer_cfg = getattr(social_cfg, 'bearer_token', None)

    # rate-limit global block
    if _is_blocked(task.owner_id, task.provider, getattr(account, 'id', None)):
        response['skipped'] = 'rate_limit_blocked'
        response['rate_limited'] = True
        raise Exception('Rate limit blocked - skipped')

    if bearer_user or bearer_cfg or has_oauth1:
        if bearer_user:
            tw_diag = TwitterClient(bearer_token=bearer_user)
        elif has_oauth1:
            tw_diag = TwitterClient(
                consumer_key=consumer_key,
                consumer_secret=consumer_secret,
                access_token=account.get_access_token(),
                access_token_secret=account.get_refresh_token(),
            )
        else:
            tw_diag = None
        if tw_diag:
            try:
                _me_body, _rl = tw_diag.get_me_with_headers()
                response['rate_limit_headers'] = _rl
                response['rate_limit_warning'] = bool(_rl.get('warning'))
                if response['rate_limit_warning']:
                    response['rate_limit_note'] = 'Twitter API 剩余配额接近阈值，请关注调用频率'
            except Exception:
                pass

    # idem+local rate guard
    idem_guard()
    rate_guard()

    if task.type == 'post':
        try:
            if has_oauth1:
                tw_post = TwitterClient(
                    consumer_key=consumer_key,
                    consumer_secret=consumer_secret,
                    access_token=account.get_access_token(),
                    access_token_secret=account.get_refresh_token(),
                )
                response['tweet'] = tw_post.post_tweet(text=text_to_post)
            elif bearer_user:
                tw_post = TwitterClient(bearer_token=bearer_user)
                response['tweet'] = tw_post.post_tweet(text=text_to_post)
        except Exception as _e:
            try:
                resp_obj = getattr(_e, 'response', None)
                if resp_obj is not None:
                    _rl = TwitterClient()._extract_rate_limit(resp_obj)
                    response['rate_limit_headers'] = _rl
                    response['rate_limit_warning'] = bool(_rl.get('warning'))
                    if response['rate_limit_warning']:
                        response['rate_limit_note'] = 'Twitter API 剩余配额接近阈值，请关注调用频率'
                    status_code = getattr(resp_obj, 'status_code', None)
                    remaining = _rl.get('x-rate-limit-remaining')
                    reset_at = _rl.get('x-rate-limit-reset')
                    should_block = (status_code == 429) or (remaining is not None and str(remaining) == '0')
                    if should_block:
                        now_ts = int(time.time())
                        ttl = None
                        if reset_at and str(reset_at).isdigit():
                            ttl = int(reset_at) - now_ts + 1
                        if not ttl or ttl <= 0:
                            ttl = int(getattr(settings, 'RATE_LIMIT_DEFAULT_BACKOFF_SECONDS', 300))
                        _block_for(task.owner_id, task.provider, getattr(account, 'id', None), ttl)
                        response['rate_limited'] = True
                        response['rate_limit_blocked_seconds'] = ttl
            except Exception:
                pass
            raise
    elif task.type == 'reply_message':
        # reply to a tweet id in payload_template.tweet_id; if missing, try search by include_keywords
        reply_to = (task.payload_template or {}).get('tweet_id')
        text = (task.payload_template or {}).get('text', '')
        if not reply_to:
            try:
                kw_cfg = None
                if getattr(task, 'keyword_config_id', None):
                    from keywords.models import KeywordConfig as _KC
                    kw_cfg = _KC.objects.filter(id=task.keyword_config_id).first()
                terms = (kw_cfg.include_keywords if kw_cfg else []) or []
                if terms:
                    # Build simple OR query. Prefix # if not present.
                    qparts = []
                    for t in terms[:5]:
                        t = (t or '').strip()
                        if not t:
                            continue
                        if t.startswith('#'):
                            qparts.append(t)
                        else:
                            qparts.append(t)
                    if qparts and (bearer_user or bearer_cfg or has_oauth1):
                        client = None
                        if bearer_user:
                            client = TwitterClient(bearer_token=bearer_user)
                        elif bearer_cfg:
                            client = TwitterClient(bearer_token=bearer_cfg)
                        elif has_oauth1:
                            client = TwitterClient(
                                consumer_key=consumer_key,
                                consumer_secret=consumer_secret,
                                access_token=account.get_access_token(),
                                access_token_secret=account.get_refresh_token(),
                            )
                        if client:
                            q = urllib.parse.quote(' OR '.join(qparts))
                            path = f"/tweets/search/recent?query={q}&max_results=10"
                            res = client._request('GET', path)
                            data = (res or {}).get('data') or []
                            if data:
                                reply_to = data[0].get('id')
            except Exception:
                pass
        if not reply_to:
            # Fallback: reply to latest of my own posts
            try:
                post = SocialPost.objects.filter(owner=task.owner, provider='twitter').order_by('-posted_at').first()
                if post and post.external_id:
                    reply_to = post.external_id
            except Exception:
                pass
        if reply_to:
            try:
                if has_oauth1:
                    tw_cli = TwitterClient(
                        consumer_key=consumer_key,
                        consumer_secret=consumer_secret,
                        access_token=account.get_access_token(),
                        access_token_secret=account.get_refresh_token(),
                    )
                elif bearer_user:
                    tw_cli = TwitterClient(bearer_token=bearer_user)
                else:
                    tw_cli = None
                if tw_cli:
                    response['tweet_reply'] = tw_cli.reply_tweet(reply_to_tweet_id=reply_to, text=text)
            except Exception as _e:
                try:
                    resp_obj = getattr(_e, 'response', None)
                    if resp_obj is not None:
                        _rl = TwitterClient()._extract_rate_limit(resp_obj)
                        response['rate_limit_headers'] = _rl
                        response['rate_limit_warning'] = bool(_rl.get('warning'))
                        if response['rate_limit_warning']:
                            response['rate_limit_note'] = 'Twitter API 剩余配额接近阈值，请关注调用频率'
                except Exception:
                    pass
                raise

