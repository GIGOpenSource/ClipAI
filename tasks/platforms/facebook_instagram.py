from typing import Dict, Any
from ..clients import FacebookClient, InstagramClient


def handle_facebook(task, social_cfg, account, text_to_post: str, response: Dict[str, Any],
                    idem_guard, rate_guard):
    if not (social_cfg and social_cfg.page_id and (social_cfg.page_access_token or account)):
        return
    idem_guard()
    rate_guard()
    page_token = (account.get_access_token() if account else None) or social_cfg.page_access_token
    fb = FacebookClient(api_version=social_cfg.api_version or 'v19.0', page_access_token=page_token, page_id=social_cfg.page_id)
    if task.type == 'post':
        response['facebook_post'] = fb.post_feed(message=text_to_post)
    elif task.type == 'reply_comment':
        cid = (task.payload_template or {}).get('comment_id')
        msg = (task.payload_template or {}).get('text', '')
        if cid:
            response['facebook_reply'] = fb.reply_comment(comment_id=cid, message=msg)


def handle_instagram(task, social_cfg, account, text_to_post: str, response: Dict[str, Any],
                     idem_guard, rate_guard):
    if not (social_cfg and social_cfg.ig_business_account_id and (social_cfg.page_access_token or account)):
        return
    idem_guard()
    rate_guard()
    page_token = (account.get_access_token() if account else None) or social_cfg.page_access_token
    ig = InstagramClient(api_version=social_cfg.api_version or 'v19.0', page_access_token=page_token, ig_business_account_id=social_cfg.ig_business_account_id)
    if task.type == 'post':
        response['ig_media'] = ig.post_media(caption=text_to_post)


