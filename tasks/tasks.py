from celery import shared_task
from django.utils import timezone
from .models import ScheduledTask, TaskRun
from .runner import execute_task
from datetime import timedelta, datetime, time as dt_time
import pytz
import os
from django.db.models.functions import TruncDay
from django.db.models import Count, Sum, Q
from stats.models import DailyStat
from stats.utils import record_success_run


@shared_task
def execute_scheduled_task(task_id: int):
    try:
        task = ScheduledTask.objects.get(id=task_id)
    except ScheduledTask.DoesNotExist:
        return {'error': 'task not found'}

    data = execute_task(task)
    resp = data.get('response', {}) or {}
    rl_hit = bool(resp.get('rate_limit_warning') or (resp.get('skipped') == 'rate_limited'))
    run = TaskRun.objects.create(
        scheduled_task=task,
        status='succeeded',
        request_dump=data['request_dump'],
        response_dump=data['response'],
        success=data['agg']['success'],
        duration_ms=data['agg']['duration_ms'],
        owner_id=data['agg']['owner_id'],
        provider=data['agg']['provider'],
        task_type=data['agg']['task_type'],
        social_config_id_used=data['used']['social_config_id_used'],
        ai_config_id_used=data['used']['ai_config_id_used'],
        keyword_config_id_used=data['used']['keyword_config_id_used'],
        prompt_config_id_used=data['used']['prompt_config_id_used'],
        sla_met=data['agg']['sla_met'],
        rate_limit_hit=rl_hit,
    )
    # Persist last external id if provided (for monitoring latest post)
    try:
        last_ext_id = data.get('agg', {}).get('last_external_id')
        if last_ext_id:
            run.external_object_id = str(last_ext_id)
            run.save(update_fields=['external_object_id'])
    except Exception:
        pass
    run.finished_at = timezone.now()
    run.save(update_fields=['finished_at'])
    task.last_run_at = run.finished_at
    task.save(update_fields=['last_run_at'])
    # Increment lightweight daily stat on success
    try:
        if run.success:
            record_success_run(owner_id=run.owner_id, provider=run.provider, task_type=run.task_type, started_date=run.started_at.date())
    except Exception:
        pass
    # Create SocialPost record on successful publish
    try:
        from .models import SocialPost
        payload = resp or {}
        provider = data['agg']['provider']
        ext_id = None
        text_used = (task.payload_template or {}).get('text', '')
        if provider == 'twitter' and isinstance(payload.get('tweet'), dict):
            ext_id = ((payload.get('tweet') or {}).get('data') or {}).get('id')
            text_used = ((payload.get('tweet') or {}).get('data') or {}).get('text') or text_used
        elif provider == 'facebook' and isinstance(payload.get('facebook_post'), dict):
            ext_id = (payload.get('facebook_post') or {}).get('id')
        elif provider == 'instagram' and isinstance(payload.get('ig_media'), dict):
            ext_id = (payload.get('ig_media') or {}).get('id')
        if ext_id:
            SocialPost.objects.create(
                owner=task.owner,
                provider=provider,
                scheduled_task=task,
                task_run=run,
                external_id=str(ext_id),
                text=text_used or '',
                payload=payload,
            )
    except Exception:
        pass
    return {'status': 'ok', 'run_id': run.id}


def _compute_next_run(now, task):
    tz = pytz.timezone(task.timezone or 'UTC')
    now_local = now.astimezone(tz)
    rt = task.recurrence_type
    if task.end_at and now >= task.end_at:
        return None
    if rt == 'once':
        return task.start_at if (task.start_at and now < task.start_at) else None
    if rt == 'minutely' and task.interval_value:
        return now + timedelta(minutes=task.interval_value)
    if rt == 'hourly' and task.interval_value:
        return now + timedelta(hours=task.interval_value)
    if rt in {'daily', 'weekly', 'monthly'}:
        tod = task.time_of_day or dt_time(0, 0)
        # next candidate base today at tod
        candidate = now_local.replace(hour=tod.hour, minute=tod.minute, second=0, microsecond=0)
        if candidate <= now_local:
            candidate += timedelta(days=1)
        if rt == 'weekly':
            days = task.weekday_mask or []
            name_to_idx = {'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6}
            wanted = {name_to_idx.get(x) for x in days if x in name_to_idx}
            for i in range(8):
                if candidate.weekday() in wanted:
                    break
                candidate += timedelta(days=1)
        if rt == 'monthly':
            dom = task.day_of_month or 1
            y, m = candidate.year, candidate.month
            # move to next month if today passed
            if candidate.day > (dom if dom > 0 else 28):
                if m == 12:
                    y, m = y + 1, 1
                else:
                    m += 1
            # naive monthly day selection
            try:
                candidate = candidate.replace(year=y, month=m, day=dom if dom > 0 else 1)
            except Exception:
                candidate = candidate.replace(year=y, month=m, day=1)
        return candidate.astimezone(pytz.UTC)
    if rt == 'cron' and task.cron_expr:
        # 简化：先按每5分钟兜底，后续可引入 croniter
        return now + timedelta(minutes=5)
    return now + timedelta(minutes=5)


@shared_task
def check_scheduled_tasks():
    now = timezone.now()
    qs = ScheduledTask.objects.filter(enabled=True).all()
    for task in qs:
        if not task.next_run_at or task.next_run_at <= now:
            execute_scheduled_task.delay(task.id)
            nxt = _compute_next_run(now, task)
            # 当上一次执行由于速率限制标记 rate_limited 时，主动推迟下一次执行，保护账号
            if getattr(task, 'last_run_at', None):
                last_runs = TaskRun.objects.filter(scheduled_task=task).order_by('-started_at')[:1]
                if last_runs:
                    rd = (last_runs[0].response_dump or {})
                    if rd.get('rate_limited') or rd.get('skipped') == 'rate_limited':
                        backoff = int(os.getenv('RATE_LIMIT_DEFAULT_BACKOFF_SECONDS', '300'))
                        nxt = now + timedelta(seconds=backoff)
            task.next_run_at = nxt
            task.save(update_fields=['next_run_at'])
    # 聚合当日已完成运行并写入 DailyStat（保留基于 TaskRun 的定期刷新）
    today = now.date()
    start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    end = timezone.make_aware(datetime.combine(today, datetime.max.time()))
    runs = TaskRun.objects.filter(started_at__gte=start, started_at__lte=end)
    # 按 owner_id 分组聚合，仅统计成功任务
    rows = runs.values('owner_id').annotate(
        ins=Count('id', filter=Q(success=True, provider='instagram')),
        x=Count('id', filter=Q(success=True, provider='twitter')),
        fb=Count('id', filter=Q(success=True, provider='facebook')),
        post_count=Count('id', filter=Q(success=True, task_type='post')),
        reply_comment_count=Count('id', filter=Q(success=True, task_type='reply_comment')),
        reply_message_count=Count('id', filter=Q(success=True, task_type='reply_message')),
        total_impressions=Sum('impressions', filter=Q(success=True)),
    )
    for r in rows:
        # account_count 使用当前活跃账号数近似
        from social.models import SocialAccount as _SA
        active_accounts = _SA.objects.filter(owner_id=r['owner_id'], status='active').count() if r['owner_id'] is not None else 0
        DailyStat.objects.update_or_create(
            date=today, owner_id=r['owner_id'],
            defaults={
                'account_count': active_accounts,
                'ins': r.get('ins') or 0,
                'x': r.get('x') or 0,
                'fb': r.get('fb') or 0,
                'post_count': r.get('post_count') or 0,
                'reply_comment_count': r.get('reply_comment_count') or 0,
                'reply_message_count': r.get('reply_message_count') or 0,
                'total_impressions': r.get('total_impressions') or 0,
            }
        )


@shared_task
def sync_twitter_following_async(account_id: int):
    """Resolve account's external_user_id if missing, then sync following into FollowTarget.

    Returns a dict with summary counts or error.
    """
    try:
        from social.models import SocialAccount, SocialConfig
        from .models import FollowTarget
        from .clients import TwitterClient
    except Exception as e:
        return {'error': f'import_failed: {e}'}

    acc = SocialAccount.objects.filter(id=account_id, provider='twitter', status='active').first()
    if not acc:
        return {'error': 'account_not_found'}

    # Build client (prefer OAuth2 bearer; fallback to OAuth1)
    bearer = None
    consumer_key = None
    consumer_secret = None
    access_token = None
    access_token_secret = None
    try:
        bearer = acc.get_access_token() or None
    except Exception:
        bearer = None
    if not bearer:
        try:
            access_token = acc.get_access_token() or None
            access_token_secret = acc.get_refresh_token() or None
        except Exception:
            access_token = None
            access_token_secret = None
        cfg = SocialConfig.objects.filter(provider='twitter', owner_id=acc.owner_id).order_by('-is_default', '-priority').first()
        if cfg and cfg.client_id and cfg.client_secret:
            consumer_key = cfg.client_id
            consumer_secret = cfg.client_secret

    cli = None
    if bearer:
        cli = TwitterClient(bearer_token=bearer)
    elif access_token and access_token_secret:
        cli = TwitterClient(consumer_key=consumer_key, consumer_secret=consumer_secret,
                            access_token=access_token, access_token_secret=access_token_secret)
    if not cli:
        return {'error': 'missing_credentials'}

    # Ensure external_user_id
    uid = acc.external_user_id
    if not uid:
        try:
            me = cli.get_me()
            uid = ((me or {}).get('data') or {}).get('id') or (me or {}).get('id')
            if uid:
                acc.external_user_id = str(uid)
                acc.save(update_fields=['external_user_id', 'updated_at'])
        except Exception as e:
            return {'error': f'resolve_uid_failed: {e}'}
    if not uid:
        return {'error': 'uid_missing'}

    # Page through following and upsert FollowTarget
    saved = 0
    token = None
    pages = 0
    while pages < 10:
        pages += 1
        try:
            page = cli.get_following(uid, pagination_token=token, max_results=100)
        except Exception as e:
            return {'error': f'fetch_following_failed: {e}', 'synced': saved}
        data = (page or {}).get('data') or []
        meta = (page or {}).get('meta') or {}
        for u in data:
            ext_id = (u or {}).get('id') or ''
            username = (u or {}).get('username') or ''
            name = (u or {}).get('name') or ''
            if not ext_id:
                continue
            FollowTarget.objects.update_or_create(
                owner_id=acc.owner_id,
                provider='twitter',
                external_user_id=str(ext_id),
                defaults={'username': username, 'display_name': name, 'source': 'imported', 'enabled': False}
            )
            saved += 1
        token = meta.get('next_token')
        if not token:
            break

    return {'status': 'ok', 'synced': saved, 'pages': pages}


