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
    has_oauth1 = bool(account and account.get_access_token() and account.get_refresh_token())

    # rate-limit global block
    if _is_blocked(task.owner_id, task.provider, getattr(account, 'id', None)):
        response['skipped'] = 'rate_limit_blocked'
        response['rate_limited'] = True
        raise Exception('Rate limit blocked - skipped')

    if has_oauth1:
        tw_diag = TwitterClient(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=account.get_access_token(),
            access_token_secret=account.get_refresh_token(),
        )
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
            if not has_oauth1:
                raise Exception('OAuth1 credentials required for Twitter write operations')
            tw_post = TwitterClient(
                consumer_key=consumer_key,
                consumer_secret=consumer_secret,
                access_token=account.get_access_token(),
                access_token_secret=account.get_refresh_token(),
            )
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
    elif task.type in {'reply_message', 'reply_comment'}:
        # Ignore payload_template IDs. Fetch my latest tweet, find its recent comments (replies), and reply to the first unreplied one.
        text = (task.payload_template or {}).get('text', '')
        if not has_oauth1:
            response['error'] = 'oauth1_required'
            return
        tw_cli = TwitterClient(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=account.get_access_token(),
            access_token_secret=account.get_refresh_token(),
        )
        # Determine my user id
        my_uid = getattr(account, 'external_user_id', None)
        if not my_uid:
            try:
                me_body = tw_cli.get_me()
                my_uid = ((me_body or {}).get('data') or {}).get('id') or (me_body or {}).get('id')
            except Exception:
                my_uid = None
        if not my_uid:
            response['error'] = 'source_user_missing'
            return
        # Fetch my latest tweet
        latest_id = None
        try:
            lst = tw_cli._request('GET', f"/users/{my_uid}/tweets?max_results=5")
            items = (lst or {}).get('data') or []
            if items:
                latest_id = items[0].get('id')
        except Exception:
            latest_id = None
        if not latest_id:
            response['skipped'] = 'no_own_tweet'
            return
        # Find recent replies in the same conversation
        reply_to = None
        try:
            res = tw_cli._request('GET', f"/tweets/search/recent?query=conversation_id:{latest_id}&max_results=10")
            data = (res or {}).get('data') or []
            for it in data:
                cmt_id = (it or {}).get('id')
                if not cmt_id or cmt_id == latest_id:
                    continue
                # skip if already replied in the last 7 days (best-effort)
                if cache.get(f"replied:tw:{task.owner_id}:{cmt_id}"):
                    continue
                reply_to = cmt_id
                break
        except Exception:
            reply_to = None
        if not reply_to:
            response['skipped'] = 'no_comments'
            return
        # Reply to the comment
        try:
            response['tweet_reply'] = tw_cli.reply_tweet(reply_to_tweet_id=reply_to, text=text)
            try:
                cache.set(f"replied:tw:{task.owner_id}:{reply_to}", 1, 7*24*3600)
            except Exception:
                pass
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

