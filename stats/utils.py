from django.db.models import F, Count, Sum, Q
from django.utils import timezone
from datetime import date as _date, datetime, timedelta
from .models import DailyStat
from social.models import SocialAccount
from tasks.models import TaskRun


def record_success_run(owner_id: int | None, provider: str, task_type: str, started_date: _date):
    """Increment DailyStat counters for a successful TaskRun.
    - provider mapping: instagram→ins, twitter→x, facebook→fb
    - type mapping: post→post_count, reply_comment→reply_comment_count, reply_message→reply_message_count
    - account_count reflects current active social accounts of the owner
    """
    prov = (provider or '').strip().lower()
    ttype = (task_type or '').strip().lower()

    # Ensure row exists
    defaults = {
        'account_count': 0,
        'ins': 0,
        'x': 0,
        'fb': 0,
        'post_count': 0,
        'reply_comment_count': 0,
        'reply_message_count': 0,
        'total_impressions': 0,
    }
    obj, _ = DailyStat.objects.get_or_create(date=started_date, owner_id=owner_id, defaults=defaults)

    # Resolve current active account count
    try:
        active_accounts = SocialAccount.objects.filter(owner_id=owner_id, status='active').count() if owner_id else 0
    except Exception:
        active_accounts = obj.account_count or 0

    updates = {
        'updated_at': timezone.now(),
        'account_count': active_accounts,
    }
    if prov == 'instagram':
        updates['ins'] = F('ins') + 1
    elif prov == 'twitter':
        updates['x'] = F('x') + 1
    elif prov == 'facebook':
        updates['fb'] = F('fb') + 1

    if ttype == 'post':
        updates['post_count'] = F('post_count') + 1
    elif ttype == 'reply_comment':
        updates['reply_comment_count'] = F('reply_comment_count') + 1
    elif ttype == 'reply_message':
        updates['reply_message_count'] = F('reply_message_count') + 1

    DailyStat.objects.filter(pk=obj.pk).update(**updates)


def rebuild_daily_stats(date_start: _date, date_end: _date, owner_id: int | None = None) -> int:
    """Rebuild DailyStat from TaskRun for the given date range.
    Returns number of rows updated/created.
    Rules:
    - Only success=True counted
    - Provider mapping: instagram→ins, twitter→x, facebook→fb
    - Type mapping: post/reply_comment/reply_message
    - total_impressions: sum of impressions over success=True
    - account_count: current active accounts per owner (approximation)
    """
    if date_start > date_end:
        date_start, date_end = date_end, date_start

    start_dt = timezone.make_aware(datetime.combine(date_start, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(date_end, datetime.max.time()))

    qs = TaskRun.objects.filter(started_at__gte=start_dt, started_at__lte=end_dt)
    if owner_id is not None:
        qs = qs.filter(owner_id=owner_id)

    # 注意：不要对 F('started_at') 调用 timezone.localtime，这会导致 'F' 对象 utcoffset 异常。
    # 采用逐日边界过滤来统计各日聚合。

    # 为了准确分天，逐天计算
    rows_updated = 0
    current = date_start
    while current <= date_end:
        day_start = timezone.make_aware(datetime.combine(current, datetime.min.time()))
        day_end = timezone.make_aware(datetime.combine(current, datetime.max.time()))
        day_qs = qs.filter(started_at__gte=day_start, started_at__lte=day_end)
        owners = list(day_qs.values_list('owner_id', flat=True).distinct())
        if owner_id is not None:
            owners = [owner_id]
        for oid in owners:
            if oid is None and owner_id is None and not owners:
                continue
            o_qs = day_qs
            if oid is not None:
                o_qs = o_qs.filter(owner_id=oid)
            agg = o_qs.aggregate(
                ins=Count('id', filter=Q(success=True, provider='instagram')),
                x=Count('id', filter=Q(success=True, provider='twitter')),
                fb=Count('id', filter=Q(success=True, provider='facebook')),
                post_count=Count('id', filter=Q(success=True, task_type='post')),
                reply_comment_count=Count('id', filter=Q(success=True, task_type='reply_comment')),
                reply_message_count=Count('id', filter=Q(success=True, task_type='reply_message')),
                total_impressions=Sum('impressions', filter=Q(success=True)),
            )
            active_accounts = SocialAccount.objects.filter(owner_id=oid, status='active').count() if oid else 0
            defaults = {
                'account_count': active_accounts,
                'ins': agg['ins'] or 0,
                'x': agg['x'] or 0,
                'fb': agg['fb'] or 0,
                'post_count': agg['post_count'] or 0,
                'reply_comment_count': agg['reply_comment_count'] or 0,
                'reply_message_count': agg['reply_message_count'] or 0,
                'total_impressions': agg['total_impressions'] or 0,
            }
            DailyStat.objects.update_or_create(date=current, owner_id=oid, defaults=defaults)
            rows_updated += 1
        current += timedelta(days=1)

    return rows_updated


