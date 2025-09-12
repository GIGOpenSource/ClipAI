from typing import Dict, Any
from ..clients import FacebookClient
from django.core.cache import cache
from ..models import SocialPost
import requests


def handle(task, social_cfg, account, text_to_post: str, response: Dict[str, Any],
           idem_guard, rate_guard):
    # 必要配置缺失：标记为错误，避免误计为成功
    if not (social_cfg and social_cfg.page_id and (social_cfg.page_access_token or account)):
        response['error'] = 'facebook_not_configured'
        return
    idem_guard()
    rate_guard()
    page_token = (account.get_access_token() if account else None) or social_cfg.page_access_token
    fb = FacebookClient(api_version=social_cfg.api_version or 'v19.0', page_access_token=page_token, page_id=social_cfg.page_id)
    if task.type == 'post':
        response['facebook_post'] = fb.post_feed(message=text_to_post)
    elif task.type == 'reply_comment':
        cid = (task.payload_template or {}).get('comment_id')
        msg = (task.payload_template or {}).get('text', '') or '感谢你的评论！'
        if not cid:
            # auto-pick latest comment from latest post of current owner
            post = SocialPost.objects.filter(owner=task.owner, provider='facebook').order_by('-posted_at').first()
            if post and post.external_id:
                try:
                    url = f"https://graph.facebook.com/{social_cfg.api_version or 'v19.0'}/{post.external_id}/comments"
                    r = requests.get(url, params={'access_token': page_token, 'limit': 5, 'summary': 'true'}, timeout=15)
                    r.raise_for_status()
                    items = (r.json() or {}).get('data') or []
                    for it in items:
                        cmt_id = it.get('id')
                        if not cmt_id:
                            continue
                        if cache.get(f"replied:fb:{task.owner_id}:{cmt_id}"):
                            continue
                        cid = cmt_id
                        break
                except Exception:
                    cid = None
        if cid:
            response['facebook_reply'] = fb.reply_comment(comment_id=cid, message=msg)
            try:
                cache.set(f"replied:fb:{task.owner_id}:{cid}", 1, 7*24*3600)
            except Exception:
                pass
    elif task.type == 'reply_message':
        # 暂不支持私信/消息回复：显式标记为不支持，避免记为成功
        response['error'] = 'unsupported_task_type'
        return
    else:
        # 其它未实现类型
        response['error'] = 'unsupported_task_type'
        return


