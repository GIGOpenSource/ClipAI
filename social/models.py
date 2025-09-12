from django.conf import settings
from django.db import models
from .utils import encrypt_text, decrypt_text


class SocialConfig(models.Model):
    PROVIDER_CHOICES = [
        ('twitter', 'Twitter'),
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('threads', 'Threads'),
    ]

    # 通用
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, help_text='社交平台')
    name = models.CharField(max_length=100, help_text='配置名称')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='social_platform_configs',
        help_text='归属用户（租户）',
        null=True,
        blank=True,
    )
    enabled = models.BooleanField(default=True, help_text='是否启用')
    is_default = models.BooleanField(default=False, help_text='平台内是否默认（唯一）')
    priority = models.IntegerField(default=0, help_text='平台内优先级，数值越大优先')

    # 通用 OAuth / 应用配置
    client_id = models.CharField(max_length=200, blank=True, help_text='客户端 ID / AppID')
    client_secret = models.CharField(max_length=300, blank=True, help_text='客户端密钥 / AppSecret')
    api_version = models.CharField(max_length=50, blank=True, help_text='API 版本（如 v19.0、2）')
    redirect_uris = models.JSONField(default=list, help_text='回调 URI 列表')
    scopes = models.JSONField(default=list, help_text='权限 scopes 列表')

    # Twitter 专用
    bearer_token = models.CharField(max_length=400, blank=True, help_text='Twitter App-only Bearer Token')

    # Facebook/Instagram 补充
    app_id = models.CharField(max_length=200, blank=True, help_text='Facebook AppID（可与 client_id 同值）')
    app_secret = models.CharField(max_length=300, blank=True, help_text='Facebook AppSecret（可与 client_secret 同值）')
    page_id = models.CharField(max_length=200, blank=True, help_text='Facebook Page ID（可选）')
    page_access_token = models.CharField(max_length=500, blank=True, help_text='Facebook Page Access Token（可选）')
    ig_business_account_id = models.CharField(max_length=200, blank=True, help_text='Instagram 业务账号 ID（可选）')

    # Webhook（可选）
    webhook_verify_token = models.CharField(max_length=200, blank=True, help_text='Webhook 验证 Token（可选）')
    signing_secret = models.CharField(max_length=300, blank=True, help_text='签名校验密钥（可选）')

    # 审计
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_social_configs',
        help_text='创建人（管理员）'
    )

    class Meta:
        ordering = ['owner_id', 'provider', '-is_default', '-priority', 'name']

    def __str__(self) -> str:
        return f"{self.provider}:{self.name}"


class SocialAccount(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('revoked', 'Revoked'),
        ('expired', 'Expired'),
    ]
    HEALTH_CHOICES = [
        ('active', 'Active'),
        ('warn', 'Warn'),
        ('banned', 'Banned'),
        ('unknown', 'Unknown'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_accounts', help_text='归属用户（租户）', null=True, blank=True)
    provider = models.CharField(max_length=32, choices=SocialConfig.PROVIDER_CHOICES, help_text='平台')
    config = models.ForeignKey(SocialConfig, on_delete=models.SET_NULL, null=True, blank=True, related_name='accounts', help_text='关联的应用配置（可选）')

    external_user_id = models.CharField(max_length=200, help_text='平台侧用户ID', blank=True, null=True)
    external_username = models.CharField(max_length=200, blank=True, help_text='平台侧用户名（可选）')

    access_token = models.TextField(blank=True, help_text='访问令牌（加密存储，开发可为明文）')
    refresh_token = models.TextField(blank=True, help_text='刷新令牌（加密存储，开发可为明文）')
    expires_at = models.DateTimeField(null=True, blank=True, help_text='令牌过期时间')
    scopes = models.JSONField(default=list, help_text='授权范围')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='active', help_text='凭据状态')
    # 健康与体检
    health_status = models.CharField(max_length=16, choices=HEALTH_CHOICES, default='unknown', help_text='健康状态')
    last_checked_at = models.DateTimeField(null=True, blank=True, help_text='上次体检时间')
    ban_reason = models.CharField(max_length=200, blank=True, help_text='封禁/异常原因（如有）')
    error_code = models.CharField(max_length=64, blank=True, help_text='最近错误码')
    failed_checks_count = models.IntegerField(default=0, help_text='连续失败次数')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['provider', 'external_user_id']),
            models.Index(fields=['owner']),
        ]
        # 仅当 external_user_id 非空时才唯一，避免空值导致唯一索引冲突
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'external_user_id'],
                name='uniq_provider_external_user_id_not_null',
                condition=~models.Q(external_user_id__isnull=True),
            )
        ]
        ordering = ['provider', 'external_username']
        verbose_name = '外部账号'
        verbose_name_plural = '外部账号'

    def __str__(self) -> str:
        return f"{self.provider}:{self.external_username or self.external_user_id}"

    # 简单的属性封装，读写时自动加解密
    def set_access_token(self, value: str | None):
        self.access_token = encrypt_text(value)

    def get_access_token(self) -> str:
        return decrypt_text(self.access_token)

    def set_refresh_token(self, value: str | None):
        self.refresh_token = encrypt_text(value)

    def get_refresh_token(self) -> str:
        return decrypt_text(self.refresh_token)

# Create your models here.
