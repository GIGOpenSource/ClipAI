from django.db import models
from .utils import encrypt_text, decrypt_text

class PoolAccount(models.Model):
    """账号池模型（全局/共享），用于执行任务时选择多个账号并行执行。

    字段：id, name, api_key, api_secret, access_token, access_token_secret, is_ban, status
    兼容多平台，使用 provider 进行标识（当前仅支持 twitter、facebook）。
    访问令牌字段采用与 SocialAccount 相同的加密读写封装。
    """

    PROVIDER_CHOICES = [
        ('twitter', 'Twitter'),
        ('facebook', 'Facebook'),
    ]
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)    # 提供商Twitter 或 Facebook
    name = models.CharField(max_length=200)                                 # 账户名称
    api_key = models.CharField(max_length=255, blank=True)
    api_secret = models.CharField(max_length=255, blank=True)
    access_token = models.TextField(blank=True)
    access_token_secret = models.TextField(blank=True)
    is_ban = models.BooleanField(default=False)
    status = models.CharField(max_length=32, default='active', help_text='active/inactive')
    USAGE_POLICY_CHOICES = [
        ('limited', 'Limited (2 per day)'),
        ('unlimited', 'Unlimited'),
    ]
    usage_policy = models.CharField(max_length=16, choices=USAGE_POLICY_CHOICES, default='unlimited', help_text='limited: 每天最多 2 次；unlimited: 不限次')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['provider', 'name']

    def __str__(self) -> str:
        return f"{self.provider}:{self.name}"

    def set_access_token(self, value: str | None):
        self.access_token = encrypt_text(value)

    def get_access_token(self) -> str:
        return decrypt_text(self.access_token)

    def set_access_token_secret(self, value: str | None):
        self.access_token_secret = encrypt_text(value)

    def get_access_token_secret(self) -> str:
        return decrypt_text(self.access_token_secret)

# Create your models her