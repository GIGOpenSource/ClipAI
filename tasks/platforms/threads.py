from typing import Dict, Any
from ..clients import ThreadsClient


def handle(task, social_cfg, account, text_to_post: str, response: Dict[str, Any],
           idem_guard, rate_guard):
    # Requirements: SocialConfig should provide api_version/user_id or use account-bound token
    access_token = (account.get_access_token() if account else None) or getattr(social_cfg, 'page_access_token', '')
    user_id = getattr(social_cfg, 'ig_business_account_id', '') or getattr(social_cfg, 'page_id', '')
    api_version = getattr(social_cfg, 'api_version', 'v1.0')

    if not (access_token and user_id):
        return

    idem_guard()
    rate_guard()

    cli = ThreadsClient(api_version=api_version, access_token=access_token, user_id=user_id)

    if task.type == 'post':
        response['threads_post'] = cli.post_text(text_to_post)


