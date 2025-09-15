from django.conf import settings
from django.db import models


class PromptConfig(models.Model):
    SCENE_CHOICES = [
        ('reply_comment', '回复评论'),
        ('reply_message', '回复消息'),
        ('post', '发帖'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='prompt_configs', help_text='归属用户')
    scene = models.CharField(max_length=32, choices=SCENE_CHOICES, help_text='使用场景')
    name = models.CharField(max_length=100, help_text='配置名称')
    content = models.TextField(help_text='提示词文本，支持变量')
    variables = models.JSONField(default=list, help_text='允许的变量名列表')
    enabled = models.BooleanField(default=True, help_text='是否启用')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['scene', 'name']

    def __str__(self) -> str:
        return f"PromptConfig({self.owner_id}, {self.scene}, {self.name})"

# Create your models here.
