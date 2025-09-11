from django.conf import settings
from django.db import models


class ScheduledTask(models.Model):
    TASK_TYPES = [
        ('reply_comment', '回复评论'),
        ('reply_message', '回复消息'),
        ('post', '发帖'),
        ('follow', '关注'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='scheduled_tasks', help_text='归属用户')
    type = models.CharField(max_length=32, choices=TASK_TYPES, help_text='任务类型')
    provider = models.CharField(max_length=32, help_text='平台，如 twitter/facebook/instagram')
    social_config_id = models.IntegerField(null=True, blank=True, help_text='覆盖用社交配置ID（可选）')
    ai_config_id = models.IntegerField(null=True, blank=True, help_text='覆盖用AI配置ID（可选）')
    keyword_config_id = models.IntegerField(null=True, blank=True, help_text='关键词配置ID（可选）')
    prompt_config_id = models.IntegerField(null=True, blank=True, help_text='提示词配置ID（可选）')
    # 话题/标签（多选）
    # 使用独立 Tag 模型，多对多绑定；用于自动拼接 #tags
    # Figma 调度字段
    RECURRENCE_CHOICES = [
        ('once', '单次'),
        ('minutely', '每N分钟'),
        ('hourly', '每N小时'),
        ('daily', '每天'),
        ('weekly', '每周'),
        ('monthly', '每月'),
        ('cron', 'Cron 表达式'),
    ]
    recurrence_type = models.CharField(max_length=16, choices=RECURRENCE_CHOICES, default='minutely')
    interval_value = models.IntegerField(null=True, blank=True, help_text='当类型为 minutely/hourly 时的间隔整数')
    time_of_day = models.TimeField(null=True, blank=True, help_text='执行时间（HH:MM），用于 daily/weekly/monthly')
    weekday_mask = models.JSONField(default=list, blank=True, help_text='周循环选择，如 ["mon","tue"]，用于 weekly')
    day_of_month = models.IntegerField(null=True, blank=True, help_text='月循环日期，1-31，支持负数代表倒数')
    timezone = models.CharField(max_length=64, default='UTC', help_text='时区名称，如 Asia/Shanghai')
    start_at = models.DateTimeField(null=True, blank=True, help_text='开始生效时间（可选）')
    end_at = models.DateTimeField(null=True, blank=True, help_text='结束生效时间（可选）')
    cron_expr = models.CharField(max_length=100, blank=True, help_text='Cron 表达式（当类型为 cron 时使用）')
    enabled = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default='idle')
    max_retries = models.IntegerField(default=3)
    rate_limit_hint = models.CharField(max_length=50, blank=True)
    sla_seconds = models.IntegerField(null=True, blank=True, help_text='SLA 目标秒数（可选）')
    payload_template = models.JSONField(default=dict, help_text='任务载荷模板（如发帖内容占位等）')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class TaskRun(models.Model):
    scheduled_task = models.ForeignKey(ScheduledTask, on_delete=models.CASCADE, related_name='runs')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default='running')
    error = models.TextField(blank=True)
    request_dump = models.JSONField(null=True, blank=True)
    response_dump = models.JSONField(null=True, blank=True)
    affected_ids = models.JSONField(default=list)
    # 统计聚合字段
    success = models.BooleanField(default=False)
    duration_ms = models.IntegerField(null=True, blank=True)
    impressions = models.IntegerField(default=0)
    owner_id = models.IntegerField(null=True, blank=True)
    provider = models.CharField(max_length=32, blank=True)
    task_type = models.CharField(max_length=32, blank=True)
    social_config_id_used = models.IntegerField(null=True, blank=True)
    ai_config_id_used = models.IntegerField(null=True, blank=True)
    keyword_config_id_used = models.IntegerField(null=True, blank=True)
    prompt_config_id_used = models.IntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    sla_met = models.BooleanField(null=True, blank=True)
    # 扩展字段
    external_object_id = models.CharField(max_length=200, blank=True)
    retry_count = models.IntegerField(default=0)
    rate_limit_hit = models.BooleanField(default=False)
    idempotency_key = models.CharField(max_length=128, blank=True)
    # AI 评估
    ai_model = models.CharField(max_length=100, blank=True)
    ai_tokens = models.JSONField(null=True, blank=True)
    ai_latency_ms = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

# Create your models here.


class SocialPost(models.Model):
    PROVIDER_CHOICES = [
        ('twitter', 'Twitter'),
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('threads', 'Threads'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_posts')
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    scheduled_task = models.ForeignKey(ScheduledTask, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts')
    task_run = models.ForeignKey(TaskRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts')
    external_id = models.CharField(max_length=200, help_text='平台返回的对象ID')
    text = models.TextField(blank=True, help_text='发布时的文本/说明')
    payload = models.JSONField(null=True, blank=True, help_text='平台返回的完整数据结构')
    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-posted_at']
        indexes = [
            models.Index(fields=['provider', 'external_id']),
            models.Index(fields=['owner']),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.external_id}"


class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


# Add M2M after Tag defined
ScheduledTask.add_to_class('tags', models.ManyToManyField(Tag, blank=True, related_name='tasks', help_text='自动拼接的标签，如 #AI #新品'))


class FollowTarget(models.Model):
    """可被关注的目标用户清单（按 owner 隔离）。"""
    SOURCE_CHOICES = [
        ('manual', '手动录入'),
        ('imported', '同步导入'),
    ]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='follow_targets')
    provider = models.CharField(max_length=32)
    external_user_id = models.CharField(max_length=100)
    username = models.CharField(max_length=200, blank=True)
    display_name = models.CharField(max_length=200, blank=True)
    note = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='manual')
    enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('owner', 'provider', 'external_user_id')
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['owner', 'provider']),
            models.Index(fields=['provider', 'external_user_id']),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.username or self.external_user_id}"


class FollowAction(models.Model):
    """关注动作记录（幂等与审计）。"""
    STATUS_CHOICES = [
        ('success', '成功'),
        ('failed', '失败'),
        ('skipped', '跳过'),
    ]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='follow_actions')
    provider = models.CharField(max_length=32)
    social_account = models.ForeignKey('social.SocialAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='follow_actions')
    target = models.ForeignKey(FollowTarget, on_delete=models.CASCADE, related_name='actions')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='success')
    error_code = models.CharField(max_length=64, blank=True)
    external_relation_id = models.CharField(max_length=200, blank=True)
    response_dump = models.JSONField(null=True, blank=True)
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-executed_at']
        indexes = [
            models.Index(fields=['owner', 'provider']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['executed_at']),
        ]

