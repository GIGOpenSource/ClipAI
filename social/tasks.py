from celery import shared_task
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from .models import SocialAccount


@shared_task
def refresh_expiring_tokens(threshold_minutes: int = 15):
    """Refresh access tokens that are going to expire soon.

    NOTE: Provider实际刷新流程需按各平台实现；此处为最小占位：
    - 仅当存在 refresh_token 且 expires_at 接近时，延长有效期，避免影响流程
    - 后续接入真实刷新接口时，在这里替换调用
    """
    now = timezone.now()
    deadline = now + timedelta(minutes=threshold_minutes)
    accounts = SocialAccount.objects.filter(
        Q(expires_at__lte=deadline) & ~Q(refresh_token='') & Q(status='active')
    )
    updated = 0
    for acc in accounts:
        # 占位刷新：将过期时间顺延 1 小时（不改 token 值）
        # 真实环境应根据 provider 调用刷新端点并更新 access_token/refresh_token/expires_at
        acc.expires_at = now + timedelta(hours=1)
        acc.save(update_fields=['expires_at', 'updated_at'])
        updated += 1
    return {'checked': accounts.count(), 'updated': updated}


@shared_task
def check_social_accounts_health():
    """Lightweight health check per account (placeholder).

    规则（占位，可替换为真实探针）：
    - status=revoked → health=banned
    - expires_at 过期 → health=expired
    - 其余 → health=active
    写入 last_checked_at；若从 active 变为 banned/expired，则 failed_checks_count+1。
    """
    now = timezone.now()
    total = 0
    changed = 0
    for acc in SocialAccount.objects.all().iterator():
        total += 1
        old_health = acc.health_status
        if acc.status == 'revoked':
            acc.health_status = 'banned'
            acc.ban_reason = acc.ban_reason or 'revoked'
        elif acc.expires_at and acc.expires_at <= now:
            acc.health_status = 'expired'
        else:
            acc.health_status = 'active'
        acc.last_checked_at = now
        if acc.health_status in ('banned', 'expired') and old_health != acc.health_status:
            acc.failed_checks_count = (acc.failed_checks_count or 0) + 1
        if old_health != acc.health_status:
            changed += 1
        acc.save(update_fields=['health_status', 'last_checked_at', 'failed_checks_count', 'ban_reason', 'updated_at'])
    return {'checked': total, 'changed': changed}


