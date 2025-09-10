from typing import Dict, Any
import time
import hashlib
from threading import Lock
import re
from django.utils import timezone
from social.models import SocialConfig
from ai.models import AIConfig
from keywords.models import KeywordConfig
from prompts.models import PromptConfig
 
from .platforms.twitter import handle as tw_handle
from .platforms.facebook_instagram import handle_facebook as fb_handle, handle_instagram as ig_handle
from ai.client import OpenAICompatibleClient
from django.conf import settings
from social.models import SocialAccount
from django.core.cache import cache
_rate_lock = Lock()
_rate_window_seconds = 60
_rate_limit_per_window = 30  # 每账号每窗口最多外呼次数（占位，可后续改为配置）
_rate_bucket: Dict[str, list[float]] = {}

_idem_lock = Lock()
_idem_ttl_seconds = 3600
_idem_seen: Dict[str, float] = {}


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


def _idem_key(task, payload: Dict[str, Any]) -> str:
    raw = f"{task.id}:{task.type}:{task.provider}:{payload}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _idem_seen_before(key: str) -> bool:
    now = time.time()
    with _idem_lock:
        # 清理过期
        for k, ts in list(_idem_seen.items()):
            if now - ts > _idem_ttl_seconds:
                _idem_seen.pop(k, None)
        if key in _idem_seen:
            return True
        _idem_seen[key] = now
        return False
 


def execute_task(task) -> Dict[str, Any]:
    started_at = timezone.now()
    owner_id = task.owner_id
    # Select SocialConfig
    social_qs = SocialConfig.objects.filter(provider=task.provider, enabled=True)
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
        if task.provider:
            kw_qs = kw_qs.filter(provider__in=['', task.provider])
        kw_cfg = kw_qs.first()

    # PromptConfig (optional)
    prompt_cfg = None
    if task.prompt_config_id:
        prompt_cfg = PromptConfig.objects.filter(id=task.prompt_config_id).first()
    else:
        prompt_cfg = PromptConfig.objects.filter(owner_id=owner_id, scene=task.type, enabled=True).first()

    # Prefer user-bound SocialAccount for runtime tokens
    account = SocialAccount.objects.filter(
        owner_id=task.owner_id, provider=task.provider, status='active'
    ).order_by('-updated_at').first()

    request_dump = {
        'social_config_id': getattr(social_cfg, 'id', None),
        'ai_config_id': getattr(ai_cfg, 'id', None),
        'keyword_config_id': getattr(kw_cfg, 'id', None),
        'prompt_config_id': getattr(prompt_cfg, 'id', None),
        'social_account_id': getattr(account, 'id', None),
        'payload_template': task.payload_template,
    }

    response: Dict[str, Any] = {'task_type': task.type, 'provider': task.provider}
    # Prepare content to post: prefer AI-generated for post tasks
    text_to_post = (task.payload_template or {}).get('text', '')
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

        if _is_blocked(task.owner_id, task.provider, getattr(account, 'id', None)):
            response['skipped'] = 'rate_limit_blocked'
            response['rate_limited'] = True
            raise Exception('Rate limit blocked - skipped')
        def idem_guard():
            idem = _idem_key(task, (task.payload_template or {}))
            if _idem_seen_before(idem):
                response['skipped'] = 'idempotent_duplicate'
                raise Exception('Skipped duplicate by idempotency key')

        def rate_guard():
            if not _rate_allow(task.owner_id, task.provider, getattr(account, 'id', None)):
                response['skipped'] = 'rate_limited'
                response['rate_limited'] = True
                raise Exception('Rate limited - skipped')

        if task.provider == 'facebook':
            fb_handle(task, social_cfg, account, text_to_post, response, idem_guard, rate_guard)
        elif task.provider == 'twitter':
            tw_handle(task, social_cfg, account, text_to_post, response, idem_guard, rate_guard)
        elif task.provider == 'instagram':
            ig_handle(task, social_cfg, account, text_to_post, response, idem_guard, rate_guard)
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
        'provider': task.provider,
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

    # 发帖不做关键词拦截，其它场景保留
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


