from typing import Dict, Any
import time
from threading import Lock
import re
from django.utils import timezone
from social.models import SocialConfig
from ai.models import AIConfig
from keywords.models import KeywordConfig
from prompts.models import PromptConfig
 
from .platforms.twitter import handle as tw_handle
from .platforms.facebook import handle as fb_handle
from .platforms.instagram import handle as ig_handle
from .platforms.threads import handle as th_handle
from ai.client import OpenAICompatibleClient
from django.conf import settings
from social.models import SocialAccount
from django.core.cache import cache
from .models import FollowTarget, FollowAction
from .clients import TwitterClient
_rate_lock = Lock()
_rate_window_seconds = 60
_rate_limit_per_window = 30  # 每账号每窗口最多外呼次数（占位，可后续改为配置）
_rate_bucket: Dict[str, list[float]] = {}

def _rate_key(owner_id: int | None, provider: str, account_id: int | None) -> str:
    return f"{owner_id or 0}:{provider}:{account_id or 0}"


def _rate_allow(owner_id: int | None, provider: str, account_id: int | None) -> bool:
    now = time.time()
    key = _rate_key(owner_id, provider, account_id)
    with _rate_lock:
        lst = _rate_bucket.get(key, [])
        # 清理窗口外记录
        lst = [t for t in lst if now - t < _rate_window_seconds]
        allowed = len(lst) < _rate_limit_per_window
        if allowed:
            lst.append(now)
            _rate_bucket[key] = lst
        else:
            _rate_bucket[key] = lst
        return allowed



def execute_task(task) -> Dict[str, Any]:
    started_at = timezone.now()
    owner_id = task.owner_id
    provider = (task.provider or '').strip().lower()
    # Select SocialConfig
    social_qs = SocialConfig.objects.filter(provider=provider, enabled=True)
    if owner_id:
        social_qs = social_qs.filter(owner_id=owner_id)
    if task.social_config_id:
        social_qs = social_qs.filter(id=task.social_config_id)
    social_cfg = social_qs.filter(is_default=True).first() or social_qs.order_by('-priority', 'name').first()

    # Select AIConfig
    ai_qs = AIConfig.objects.filter(enabled=True)
    if task.ai_config_id:
        ai_qs = ai_qs.filter(id=task.ai_config_id)
    ai_cfg = ai_qs.filter(is_default=True).first() or ai_qs.order_by('-priority', 'name').first()

    # KeywordConfig (optional)
    kw_cfg = None
    if task.keyword_config_id:
        kw_cfg = KeywordConfig.objects.filter(id=task.keyword_config_id).first()
    else:
        kw_qs = KeywordConfig.objects.filter(enabled=True)
        if owner_id:
            kw_qs = kw_qs.filter(owner_id=owner_id)
        if provider:
            kw_qs = kw_qs.filter(provider__in=['', provider])
        kw_cfg = kw_qs.first()

    # PromptConfig (optional)
    prompt_cfg = None
    if task.prompt_config_id:
        prompt_cfg = PromptConfig.objects.filter(id=task.prompt_config_id).first()
    else:
        prompt_cfg = PromptConfig.objects.filter(owner_id=owner_id, scene=task.type, enabled=True).first()

    # Prefer user-bound SocialAccount for runtime tokens
    account = SocialAccount.objects.filter(
        owner_id=task.owner_id, provider=provider, status='active'
    ).order_by('-updated_at').first()

    request_dump = {
        'social_config_id': getattr(social_cfg, 'id', None),
        'ai_config_id': getattr(ai_cfg, 'id', None),
        'keyword_config_id': getattr(kw_cfg, 'id', None),
        'prompt_config_id': getattr(prompt_cfg, 'id', None),
        'social_account_id': getattr(account, 'id', None),
        'payload_template': task.payload_template,
    }

    response: Dict[str, Any] = {'task_type': task.type, 'provider': provider}
    # Prepare content to post: prefer AI-generated for post tasks
    text_to_post = (task.payload_template or {}).get('text', '')
    # Append tags (#tag) if any (use task.tags only)
    try:
        tag_names = [t.name for t in task.tags.all()][:5]
        if tag_names:
            tail = ' ' + ' '.join('#' + n.lstrip('#') for n in tag_names)
            if text_to_post:
                text_to_post = (text_to_post + tail).strip()
            # AI 生成后也会覆盖 text_to_post，再补一遍在下方
    except Exception:
        pass
    if task.type == 'post':
        if ai_cfg and ai_cfg.api_key:
            try:
                client = OpenAICompatibleClient(
                    base_url=ai_cfg.base_url or 'https://api.openai.com',
                    api_key=ai_cfg.api_key,
                )
                payload = (task.payload_template or {})
                base_text = payload.get('text', '')
                system_prompt = (getattr(prompt_cfg, 'content', '') or '你是一个社交媒体助理，请生成合适的简短中文内容。')
                variables = getattr(prompt_cfg, 'variables', []) or []
                for var in variables:
                    placeholder = '{' + str(var) + '}'
                    value = str(payload.get(var, ''))
                    system_prompt = system_prompt.replace(placeholder, value)
                messages = [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': base_text or f'请根据类型 {task.type} 与平台 {task.provider} 生成一句适合发布或回复的中文内容。'}
                ]
                ai_res = client.chat_completion(model=ai_cfg.model, messages=messages)
                ai_text = ai_res.get('content') or ''
                if ai_text:
                    text_to_post = ai_text
                    # re-append tags after AI text
                    try:
                        tag_names = [t.name for t in task.tags.all()][:5]
                        if tag_names:
                            text_to_post = (text_to_post + ' ' + ' '.join('#' + n.lstrip('#') for n in tag_names)).strip()
                    except Exception:
                        pass
                    response['ai_generated'] = True
                    response['ai_meta'] = {
                        'latency_ms': ai_res.get('latency_ms'),
                        'tokens': ai_res.get('tokens'),
                        'model': ai_cfg.model,
                        'provider': ai_cfg.provider,
                    }
                else:
                    response['ai_generated'] = False
            except Exception as e:
                response['ai_error'] = str(e)
                response['ai_generated'] = False
    try:
        # Global rate-limit block (owner+provider+account)
        def _block_key(oid, prov, aid):
            return f"rl:block:{oid or 0}:{prov}:{aid or 0}"

        def _is_blocked(oid, prov, aid) -> bool:
            return bool(cache.get(_block_key(oid, prov, aid)))

        def _block_for(oid, prov, aid, seconds: int):
            if seconds and seconds > 0:
                cache.set(_block_key(oid, prov, aid), 1, timeout=seconds)

        if _is_blocked(task.owner_id, provider, getattr(account, 'id', None)):
            response['skipped'] = 'rate_limit_blocked'
            response['rate_limited'] = True
            raise Exception('Rate limit blocked - skipped')
        def idem_guard():
            # 全局关闭幂等拦截
            return

        def rate_guard():
            if not _rate_allow(task.owner_id, provider, getattr(account, 'id', None)):
                response['skipped'] = 'rate_limited'
                response['rate_limited'] = True
                raise Exception('Rate limited - skipped')

        if provider == 'facebook':
            fb_handle(task, social_cfg, account, text_to_post, response, idem_guard, rate_guard)
        elif provider == 'twitter' and task.type != 'follow':
            tw_handle(task, social_cfg, account, text_to_post, response, idem_guard, rate_guard)
        elif provider == 'instagram':
            ig_handle(task, social_cfg, account, text_to_post, response, idem_guard, rate_guard)
        elif provider == 'threads':
            th_handle(task, social_cfg, account, text_to_post, response, idem_guard, rate_guard)
        elif provider == 'twitter' and task.type == 'follow':
            # Handle follow flow
            try:
                # Select targets
                daily_cap = None
                try:
                    # 优先使用显式字段，其次兼容 payload_template.daily_cap
                    explicit_cap = getattr(task, 'follow_daily_cap', None)
                    daily_cap = int(explicit_cap or (task.payload_template or {}).get('daily_cap') or 0) or None
                except Exception:
                    daily_cap = None
                if not _enforce_daily_cap(task.owner_id, provider, daily_cap):
                    response['skipped'] = 'daily_cap_reached'
                    raise Exception('Daily cap reached')

                targets = _select_follow_targets(task, task.owner_id)
                response['follow_candidates'] = [
                    {
                        'id': t.id,
                        'ext': (t.external_user_id or t.username or ''),
                        'username': t.username
                    }
                    for t in targets
                ]
                followed = []
                if targets:
                    for tgt in targets:
                        # 针对每个目标，优先使用其绑定的 runner_accounts；否则使用最近更新的账号
                        try:
                            target_runner_accounts = list(getattr(tgt, 'runner_accounts').all())
                        except Exception:
                            target_runner_accounts = []
                        if not target_runner_accounts and account:
                            target_runner_accounts = [account]

                        # 若该目标已成功关注，标记跳过
                        if FollowAction.objects.filter(owner_id=task.owner_id, provider='twitter', target=tgt, status='success').exists():
                            for acc in target_runner_accounts:
                                FollowAction.objects.create(owner_id=task.owner_id, provider='twitter', social_account=acc, target=tgt, status='skipped', error_code='already_followed')
                            continue

                        for acc in target_runner_accounts:
                            # 全局阻断检查（缓存）
                            try:
                                if _is_blocked(task.owner_id, provider, getattr(acc, 'id', None)):
                                    FollowAction.objects.create(owner_id=task.owner_id, provider='twitter', social_account=acc, target=tgt, status='skipped', error_code='rate_limit_blocked')
                                    continue
                            except Exception:
                                pass

                            # 本地速率限制（按 owner+provider+account）
                            if not _rate_allow(task.owner_id, provider, getattr(acc, 'id', None)):
                                response['rate_limited'] = True
                                FollowAction.objects.create(owner_id=task.owner_id, provider='twitter', social_account=acc, target=tgt, status='skipped', error_code='rate_limited')
                                continue

                            # OAuth1 客户端
                            consumer_key = getattr(social_cfg, 'client_id', '') or None
                            consumer_secret = getattr(social_cfg, 'client_secret', '') or None
                            access_token = acc.get_access_token() if acc else None
                            access_token_secret = acc.get_refresh_token() if acc else None

                            cli: TwitterClient | None = None
                            if access_token and access_token_secret and consumer_key and consumer_secret:
                                cli = TwitterClient(
                                    consumer_key=consumer_key,
                                    consumer_secret=consumer_secret,
                                    access_token=access_token,
                                    access_token_secret=access_token_secret,
                                )
                            if not cli:
                                FollowAction.objects.create(owner_id=task.owner_id, provider='twitter', social_account=acc, target=tgt, status='failed', error_code='oauth1_required')
                                continue

                            # 源用户ID：优先用绑定账号表里的 external_user_id，避免额外调 /users/me
                            source_uid = getattr(acc, 'external_user_id', None)
                            if not source_uid:
                                me = cli.get_me()
                                source_uid = ((me or {}).get('data') or {}).get('id') or (me or {}).get('id')
                            if not source_uid:
                                FollowAction.objects.create(owner_id=task.owner_id, provider='twitter', social_account=acc, target=tgt, status='failed', error_code='source_user_missing')
                                continue

                            try:
                                target_uid = tgt.external_user_id
                                if not target_uid and tgt.username:
                                    info = cli.get_user_by_username(tgt.username)
                                    target_uid = ((info or {}).get('data') or {}).get('id')
                                    if not target_uid:
                                        FollowAction.objects.create(owner_id=task.owner_id, provider='twitter', social_account=acc, target=tgt, status='failed', error_code='target_not_found')
                                        continue
                                # 避免误对自己执行关注
                                if str(target_uid) == str(source_uid):
                                    FollowAction.objects.create(owner_id=task.owner_id, provider='twitter', social_account=acc, target=tgt, status='skipped', error_code='self_follow')
                                    continue
                                res = cli.follow_user(source_user_id=source_uid, target_user_id=target_uid)
                                FollowAction.objects.create(owner_id=task.owner_id, provider='twitter', social_account=acc, target=tgt, status='success', response_dump=res)
                                try:
                                    tgt.completed = True
                                    tgt.save(update_fields=['completed', 'updated_at'])
                                except Exception:
                                    pass
                                followed.append({'target': tgt.id, 'external_user_id': target_uid, 'social_account_id': acc.id})
                                # 任一账号成功则该目标完成
                                break
                            except Exception as e:
                                # Try extract rate limit and set block
                                try:
                                    resp_obj = getattr(e, 'response', None)
                                    if resp_obj is not None:
                                        _rl = TwitterClient()._extract_rate_limit(resp_obj)
                                        response['rate_limit_headers'] = _rl
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
                                            cache.set(_rate_key(task.owner_id, provider, getattr(acc, 'id', None)), 1, timeout=ttl)
                                            response['rate_limited'] = True
                                            response['rate_limit_blocked_seconds'] = ttl
                                except Exception:
                                    pass
                                FollowAction.objects.create(owner_id=task.owner_id, provider='twitter', social_account=acc, target=tgt, status='failed', error_code='follow_failed')
                                # 若该账号被限速，尝试下一个账号/目标
                                if response.get('rate_limited'):
                                    continue

                response['followed'] = followed
            except Exception as e:
                response['error'] = str(e)
    except Exception as exc:
        response['error'] = str(exc)
    finished_at = timezone.now()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    success = 'error' not in response
    sla_met = None
    if task.sla_seconds is not None:
        sla_met = duration_ms <= (task.sla_seconds * 1000)

    used = {
        'social_config_id_used': request_dump['social_config_id'],
        'ai_config_id_used': request_dump['ai_config_id'],
        'keyword_config_id_used': request_dump['keyword_config_id'],
        'prompt_config_id_used': request_dump['prompt_config_id'],
    }

    agg = {
        'success': success,
        'duration_ms': duration_ms,
        'owner_id': task.owner_id,
        'provider': provider,
        'task_type': task.type,
        'sla_met': sla_met,
    }

    # Track last created external id for quick monitoring
    last_id = None
    try:
        if response.get('tweet') and isinstance(response['tweet'], dict):
            last_id = (response['tweet'].get('data') or {}).get('id')
        elif response.get('facebook_post') and isinstance(response['facebook_post'], dict):
            last_id = response['facebook_post'].get('id')
        elif response.get('ig_media') and isinstance(response['ig_media'], dict):
            last_id = response['ig_media'].get('id')
    except Exception:
        pass
    if last_id:
        try:
            from .models import TaskRun
            # Note: TaskRun creation happens in view; here we only return id; views will persist.
            agg['last_external_id'] = last_id
        except Exception:
            pass
    return {'request_dump': request_dump, 'response': response, 'agg': agg, 'used': used}


def _select_follow_targets(task, owner_id: int) -> list[FollowTarget]:
    payload = task.payload_template or {}
    # 1) 显式 M2M 绑定
    try:
        if hasattr(task, 'follow_targets'):
            bound = list(task.follow_targets.all())
            if bound:
                return bound
    except Exception:
        pass
    # 2) 兼容 legacy target_ids
    ids = payload.get('target_ids') or []
    qs = FollowTarget.objects.filter(owner_id=owner_id, provider=task.provider, completed=False)
    if ids:
        return list(qs.filter(id__in=ids, enabled=True)[:100])
    # 3) 默认：按限制挑选（优先 follow_max_per_run 其次 payload_template.max_per_run）
    limit = None
    try:
        limit = int(getattr(task, 'follow_max_per_run') or 0) or None
    except Exception:
        limit = None
    if not limit:
        limit = int(payload.get('max_per_run') or 5)
    return list(qs.filter(enabled=True).order_by('-updated_at')[:max(1, min(100, limit))])


def _enforce_daily_cap(owner_id: int, provider: str, cap: int | None) -> bool:
    if not cap:
        return True
    from django.utils import timezone as _tz
    start = _tz.now().replace(hour=0, minute=0, second=0, microsecond=0)
    count = FollowAction.objects.filter(owner_id=owner_id, provider=provider, executed_at__gte=start, status='success').count()
    return count < cap



def generate_ai_preview(task) -> Dict[str, Any]:
    """Generate AI text preview for a task without external calls.
    Returns: { content: str, ai_meta: {...}, blocked: bool, reason: str }
    """
    # Select AI/Keyword/Prompt similar to execute_task
    ai_qs = AIConfig.objects.filter(enabled=True)
    if task.ai_config_id:
        ai_qs = ai_qs.filter(id=task.ai_config_id)
    ai_cfg = ai_qs.filter(is_default=True).first() or ai_qs.order_by('-priority', 'name').first()

    kw_cfg = None
    if task.keyword_config_id:
        kw_cfg = KeywordConfig.objects.filter(id=task.keyword_config_id).first()
    else:
        kw_qs = KeywordConfig.objects.filter(enabled=True)
        if task.owner_id:
            kw_qs = kw_qs.filter(owner_id=task.owner_id)
        if task.provider:
            kw_qs = kw_qs.filter(provider__in=['', task.provider])
        kw_cfg = kw_qs.first()

    prompt_cfg = None
    if task.prompt_config_id:
        prompt_cfg = PromptConfig.objects.filter(id=task.prompt_config_id).first()
    else:
        prompt_cfg = PromptConfig.objects.filter(owner_id=task.owner_id, scene=task.type, enabled=True).first()

    payload = (task.payload_template or {})
    base_text = payload.get('text', '')

    # keyword filter
    def _match_keywords(text: str) -> bool:
        if not kw_cfg:
            return True
        include = kw_cfg.include_keywords or []
        exclude = kw_cfg.exclude_keywords or []
        mode = (kw_cfg.match_mode or 'any')
        text_l = text or ''
        for w in exclude:
            if w and w in text_l:
                return False
        if not include:
            return True
        if mode == 'all':
            return all((w in text_l) for w in include if w)
        if mode == 'regex':
            try:
                return any(re.search(p, text_l) for p in include if p)
            except re.error:
                return any((w in text_l) for w in include if w)
        return any((w in text_l) for w in include if w)

    # 发帖不做关键词拦截，其它场景保留；follow 预览直接返回候选列表
    if task.type == 'follow':
        targets = [
            {'id': t.id, 'ext': t.external_user_id, 'username': t.username}
            for t in _select_follow_targets(task, task.owner_id)
        ]
        return {'content': '', 'blocked': False, 'targets': targets}
    if task.type != 'post':
        if not _match_keywords(base_text):
            return {'content': '', 'blocked': True, 'reason': 'keyword_filter_blocked'}

    if not (ai_cfg and ai_cfg.api_key):
        return {'content': '', 'blocked': False, 'reason': 'no_ai_config'}

    # build prompt
    system_prompt = (getattr(prompt_cfg, 'content', '') or '你是一个社交媒体助理，请生成合适的简短中文内容。')
    variables = getattr(prompt_cfg, 'variables', []) or []
    for var in variables:
        placeholder = '{' + str(var) + '}'
        value = str(payload.get(var, ''))
        system_prompt = system_prompt.replace(placeholder, value)

    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': base_text or f'请根据类型 {task.type} 与平台 {task.provider} 生成一句适合发布或回复的中文内容。'}
    ]
    try:
        client = OpenAICompatibleClient(
            base_url=ai_cfg.base_url or 'https://api.openai.com',
            api_key=ai_cfg.api_key,
        )
        res = client.chat_completion(model=ai_cfg.model, messages=messages)
        return {
            'content': res.get('content') or '',
            'ai_meta': {
                'latency_ms': res.get('latency_ms'),
                'tokens': res.get('tokens'),
                'model': ai_cfg.model,
                'provider': ai_cfg.provider,
            },
            'blocked': False,
        }
    except Exception as exc:
        # 预览模式下不抛异常，返回可诊断信息
        return {
            'content': '',
            'blocked': False,
            'reason': 'ai_error',
            'error': str(exc),
        }


