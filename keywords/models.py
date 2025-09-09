from django.conf import settings
from django.db import models


class KeywordConfig(models.Model):
    MATCH_CHOICES = [
        ('any', '匹配其中任意一个'),
        ('all', '匹配全部'),
        ('regex', '正则匹配'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='keyword_configs', help_text='归属用户')
    name = models.CharField(max_length=100, blank=True, null=True, help_text='配置名称（可选）')
    provider = models.CharField(max_length=32, blank=True, help_text='可选：平台过滤，如 twitter/facebook/instagram')
    include_keywords = models.JSONField(default=list, help_text='包含关键词列表')
    exclude_keywords = models.JSONField(default=list, help_text='排除关键词列表')
    match_mode = models.CharField(max_length=10, choices=MATCH_CHOICES, default='any', help_text='匹配模式')
    enabled = models.BooleanField(default=True, help_text='是否启用')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self) -> str:
        return f"KeywordConfig({self.owner_id}, {self.provider or 'all'})"

# Create your models here.
