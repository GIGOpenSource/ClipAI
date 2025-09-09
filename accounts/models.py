from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text='执行该操作的管理员（可能为空，表示系统行为）'
    )
    action = models.CharField(max_length=128, help_text='动作名称，例如 user.activate / role.set_permissions')
    target_type = models.CharField(max_length=128, help_text='目标对象类型，例如 user / role / permission')
    target_id = models.CharField(max_length=128, blank=True, help_text='目标对象 ID，若无可留空')
    timestamp = models.DateTimeField(auto_now_add=True, help_text='服务器记录时间（UTC）')
    ip_address = models.GenericIPAddressField(null=True, blank=True, help_text='发起请求的 IP 地址')
    user_agent = models.CharField(max_length=512, blank=True, help_text='发起请求的 User-Agent')
    success = models.BooleanField(default=True, help_text='是否执行成功')
    metadata = models.JSONField(null=True, blank=True, help_text='补充上下文信息（JSON）')

    class Meta:
        ordering = ['-timestamp']

    def __str__(self) -> str:
        return f"{self.timestamp} {self.action} {self.target_type}#{self.target_id}"
