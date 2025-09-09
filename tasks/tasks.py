from celery import shared_task
from django.utils import timezone
from .models import ScheduledTask, TaskRun
from .runner import execute_task
from datetime import timedelta, datetime, time as dt_time
import pytz
from django.db.models.functions import TruncDay
from django.db.models import Count, Sum, Q
from stats.models import DailyStat


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
    run.finished_at = timezone.now()
    run.save(update_fields=['finished_at'])
    task.last_run_at = run.finished_at
    task.save(update_fields=['last_run_at'])
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
    # 聚合昨日已完成运行并写入 DailyStat（简化：每次扫描也顺带刷新最近一天统计）
    today = now.date()
    start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    end = timezone.make_aware(datetime.combine(today, datetime.max.time()))
    runs = TaskRun.objects.filter(started_at__gte=start, started_at__lte=end)
    # 按 owner_id 分组聚合，分别写入 DailyStat
    rows = runs.values('owner_id').annotate(
        account_count=Count('social_config_id_used', distinct=True),
        ins=Count('id', filter=Q(provider='instagram')),
        x=Count('id', filter=Q(provider='twitter')),
        fb=Count('id', filter=Q(provider='facebook')),
        post_count=Count('id', filter=Q(task_type='post')),
        reply_comment_count=Count('id', filter=Q(task_type='reply_comment')),
        reply_message_count=Count('id', filter=Q(task_type='reply_message')),
        total_impressions=Sum('impressions'),
    )
    for r in rows:
        DailyStat.objects.update_or_create(
            date=today, owner_id=r['owner_id'],
            defaults={
                'account_count': r.get('account_count') or 0,
                'ins': r.get('ins') or 0,
                'x': r.get('x') or 0,
                'fb': r.get('fb') or 0,
                'post_count': r.get('post_count') or 0,
                'reply_comment_count': r.get('reply_comment_count') or 0,
                'reply_message_count': r.get('reply_message_count') or 0,
                'total_impressions': r.get('total_impressions') or 0,
            }
        )


