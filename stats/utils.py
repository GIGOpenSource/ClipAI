from django.db.models import F
from django.utils import timezone
from datetime import date as _date
from .models import DailyStat


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
        'twitter': 0,
        'fb': 0,
        'post_count': 0,
        'reply_comment_count': 0,
        'reply_message_count': 0,
        'total_impressions': 0,
    }
    obj, _ = DailyStat.objects.get_or_create(date=started_date, owner_id=owner_id, defaults=defaults)

    # Resolve current active account count（简化：不再依赖外部账号表，保持现值）
    active_accounts = obj.account_count or 0

    updates = {
        'updated_at': timezone.now(),
        'account_count': active_accounts,
    }
    if prov == 'instagram':
        updates['ins'] = F('ins') + 1
    elif prov == 'twitter':
        updates['twitter'] = F('twitter') + 1
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
    """Deprecated in simplified mode: no-op, keep for admin compatibility."""
    return 0
    