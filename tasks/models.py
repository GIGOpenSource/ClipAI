from django.utils import timezone
from django.conf import settings
from django.db import models
from social.models import PoolAccount
from prompts.models import PromptConfig


class SimpleTask(models.Model):
    """非定时任务配置：一次性触发，支持选择多个账号池账号并行执行。

    type: post / reply_comment
    provider: twitter / facebook
    fields for composition: text, mentions, tags (<=5)
    selected_accounts: 多选 PoolAccount
    """
    TASK_TYPES = [
        ('post', '发帖'),
        ('reply_comment', '回复评论'),
    ]
    PROVIDER_CHOICES = [
        ('twitter', 'Twitter'),
        ('facebook', 'Facebook'),
    ]
    LANGUAGE_CHOICES = [
        ('auto', 'Auto'),
        ('zh', 'Chinese'),
        ('en', 'English'),
        ('ja', 'Japanese'),
        ('ko', 'Korean'),
        ('es', 'Spanish'),
        ('fr', 'French'),
        ('de', 'German'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='simple_tasks')
    type = models.CharField(max_length=32, choices=TASK_TYPES)
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    language = models.CharField(max_length=8, choices=LANGUAGE_CHOICES, default='auto', help_text='AI 生成文案语言')
    text = models.TextField(blank=True)
    mentions = models.JSONField(default=list, help_text='可@的人用户名/ID 列表')
    # mentions = models.TextField(default=list, help_text='可@的人用户名/ID 列表')
    tags = models.JSONField(default=list, help_text='最多 5 个话题标签（字符串，不含#）')
    payload = models.JSONField(default=dict, help_text='平台相关附加参数，如 comment_id 等')
    selected_accounts = models.ManyToManyField(PoolAccount, blank=True, related_name='simple_tasks')
    prompt = models.ForeignKey(PromptConfig, null=True, blank=True, on_delete=models.SET_NULL, related_name='tasks', help_text='执行所用提示词（系统内容）')
    last_status = models.CharField(max_length=16, default='new', help_text='new/success/partial/error')
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_success = models.BooleanField(default=False, help_text='上次执行是否全部成功')
    last_failed = models.BooleanField(default=False, help_text='上次执行是否存在失败')
    task_remark = models.CharField(max_length=255, blank=True, help_text='备注信息')
    last_text = models.TextField(blank=True, help_text='上次实际发送的最终文案（含 tags/mentions）')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class SimpleTaskRun(models.Model):
    """每次执行的明细记录（便于统计和审计）。"""
    TASK_TYPES = [
        ('post', '发帖'),
        ('reply_comment', '回复评论'),
    ]
    PROVIDER_CHOICES = [
        ('twitter', 'Twitter'),
        ('facebook', 'Facebook'),
    ]

    task = models.ForeignKey(SimpleTask, on_delete=models.CASCADE, related_name='runs')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='simple_task_runs')
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    type = models.CharField(max_length=32, choices=TASK_TYPES)
    account = models.ForeignKey(PoolAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_runs')

    text = models.TextField(help_text='本次实际发送文案（含 tags/mentions）')
    used_prompt = models.CharField(max_length=200, blank=True)
    ai_model = models.CharField(max_length=100, blank=True)
    ai_provider = models.CharField(max_length=50, blank=True)

    success = models.BooleanField(default=False)
    external_id = models.CharField(max_length=100, blank=True, help_text='平台返回的对象ID，如 tweet_id 或 post_id')
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"Run(task={self.task_id}, provider={self.provider}, success={self.success})"


class Tweet(models.Model):
    """
    推文主表模型
    """
    tweet_id = models.CharField(max_length=50, unique=True, verbose_name="推文ID")
    platform = models.CharField(max_length=100, verbose_name="平台名")
    # 统计数据
    publish_count = models.IntegerField(default=0, verbose_name="发布数")
    impression_count = models.IntegerField(default=0, verbose_name="曝光量(浏览量)")
    comment_count = models.IntegerField(default=0, verbose_name="评论数")
    message_count = models.IntegerField(default=0, verbose_name="消息数(私信预留)")
    like_count = models.IntegerField(default=0, verbose_name="点赞数")
    click_count = models.IntegerField(default=0, verbose_name="点击量(前台预留)")
    created_date = models.DateField(default=timezone.now, verbose_name="创建日期")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = 't_tweets'
        verbose_name = '推文'
        verbose_name_plural = '推文'

    def __str__(self):
        return f"Tweet {self.tweet_id} on {self.platform}"


class TweetComment(models.Model):
    """
    推文评论表模型
    """
    comment_id = models.CharField(max_length=50, unique=True, verbose_name="评论ID")
    tweet = models.ForeignKey(Tweet, on_delete=models.CASCADE, related_name='comments', verbose_name="推文")

    content = models.TextField(verbose_name="评论内容")
    commenter_id = models.CharField(max_length=50, verbose_name="评论人ID")
    commenter_nickname = models.CharField(max_length=100, verbose_name="评论人昵称")

    # 回复相关字段
    reply_to_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="回复人ID")
    reply_to_nickname = models.CharField(max_length=100, blank=True, null=True, verbose_name="回复人昵称")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = 't_tweet_comments'
        verbose_name = '推文评论'
        verbose_name_plural = '推文评论'
        indexes = [
            models.Index(fields=['tweet_id']),
            models.Index(fields=['commenter_id']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Comment {self.comment_id} on Tweet {self.tweet.tweet_id}"