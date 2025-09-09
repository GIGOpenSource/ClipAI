from django.conf import settings
from django.db import models


class AIConfig(models.Model):
    PROVIDER_CHOICES = [
        ('openai', 'OpenAI'),
        ('azure_openai', 'Azure OpenAI'),
        ('anthropic', 'Anthropic'),
        ('google', 'Google Gemini'),
        ('deepseek', 'DeepSeek'),
        ('custom', 'Custom'),
    ]

    name = models.CharField(max_length=100, unique=True, help_text='配置名称')
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, help_text='厂商')
    model = models.CharField(max_length=100, help_text='模型名称/版本')
    enabled = models.BooleanField(default=True, help_text='是否启用')
    is_default = models.BooleanField(default=False, help_text='是否设为默认（全局唯一）')
    priority = models.IntegerField(default=0, help_text='优先级，数值越大优先')

    # 凭据与连接
    api_key = models.CharField(max_length=256, help_text='访问密钥，读取时应掩码')
    base_url = models.URLField(blank=True, help_text='自定义 API Base URL（代理/Azure 场景）')
    region = models.CharField(max_length=50, blank=True, help_text='区域（Azure 等需要）')
    api_version = models.CharField(max_length=50, blank=True, help_text='API 版本（Azure/OpenAI 兼容接口）')
    organization_id = models.CharField(max_length=100, blank=True, help_text='组织/项目标识（可选）')

    # 审计
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_ai_configs',
        help_text='创建人（管理员）'
    )

    class Meta:
        ordering = ['-is_default', '-priority', 'name']

    def __str__(self) -> str:
        return f"{self.name} ({self.provider}:{self.model})"

# Create your models here.
