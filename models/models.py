# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AccountsAuditlog(models.Model):
    id = models.BigAutoField(primary_key=True)
    action = models.CharField(max_length=128)
    target_type = models.CharField(max_length=128)
    target_id = models.CharField(max_length=128)
    timestamp = models.DateTimeField()
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=512)
    success = models.BooleanField()
    metadata = models.JSONField(blank=True, null=True)
    actor = models.ForeignKey('AuthUser', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'accounts_auditlog'


class AiAiconfig(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(unique=True, max_length=100)
    provider = models.CharField(max_length=32)
    model = models.CharField(max_length=100)
    enabled = models.BooleanField()
    is_default = models.BooleanField()
    priority = models.IntegerField()
    api_key = models.CharField(max_length=256)
    base_url = models.CharField(max_length=200)
    region = models.CharField(max_length=50)
    api_version = models.CharField(max_length=50)
    organization_id = models.CharField(max_length=100)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    created_by = models.ForeignKey('AuthUser', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ai_aiconfig'


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.BooleanField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.BooleanField()
    is_active = models.BooleanField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class BackgroundTask(models.Model):
    id = models.BigAutoField(primary_key=True)
    task_name = models.CharField(max_length=190)
    task_params = models.TextField()
    task_hash = models.CharField(max_length=40)
    verbose_name = models.CharField(max_length=255, blank=True, null=True)
    priority = models.IntegerField()
    run_at = models.DateTimeField()
    repeat = models.BigIntegerField()
    repeat_until = models.DateTimeField(blank=True, null=True)
    queue = models.CharField(max_length=190, blank=True, null=True)
    attempts = models.IntegerField()
    failed_at = models.DateTimeField(blank=True, null=True)
    last_error = models.TextField()
    locked_by = models.CharField(max_length=64, blank=True, null=True)
    locked_at = models.DateTimeField(blank=True, null=True)
    creator_object_id = models.IntegerField(blank=True, null=True)
    creator_content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'background_task'


class BackgroundTaskCompletedtask(models.Model):
    id = models.BigAutoField(primary_key=True)
    task_name = models.CharField(max_length=190)
    task_params = models.TextField()
    task_hash = models.CharField(max_length=40)
    verbose_name = models.CharField(max_length=255, blank=True, null=True)
    priority = models.IntegerField()
    run_at = models.DateTimeField()
    repeat = models.BigIntegerField()
    repeat_until = models.DateTimeField(blank=True, null=True)
    queue = models.CharField(max_length=190, blank=True, null=True)
    attempts = models.IntegerField()
    failed_at = models.DateTimeField(blank=True, null=True)
    last_error = models.TextField()
    locked_by = models.CharField(max_length=64, blank=True, null=True)
    locked_at = models.DateTimeField(blank=True, null=True)
    creator_object_id = models.IntegerField(blank=True, null=True)
    creator_content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'background_task_completedtask'


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.SmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoApschedulerDjangojob(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    next_run_time = models.DateTimeField(blank=True, null=True)
    job_state = models.BinaryField()

    class Meta:
        managed = False
        db_table = 'django_apscheduler_djangojob'


class DjangoApschedulerDjangojobexecution(models.Model):
    id = models.BigAutoField(primary_key=True)
    status = models.CharField(max_length=50)
    run_time = models.DateTimeField()
    duration = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    finished = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    exception = models.CharField(max_length=1000, blank=True, null=True)
    traceback = models.TextField(blank=True, null=True)
    job = models.ForeignKey(DjangoApschedulerDjangojob, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_apscheduler_djangojobexecution'
        unique_together = (('job', 'run_time'),)


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class PromptsPromptconfig(models.Model):
    id = models.BigAutoField(primary_key=True)
    scene = models.CharField(max_length=32)
    name = models.CharField(max_length=100)
    content = models.TextField()
    variables = models.JSONField()
    enabled = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    owner = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'prompts_promptconfig'


class SocialPoolaccount(models.Model):
    id = models.BigAutoField(primary_key=True)
    provider = models.CharField(max_length=32)
    name = models.CharField(max_length=200)
    api_key = models.CharField(max_length=255)
    api_secret = models.CharField(max_length=255)
    access_token = models.TextField()
    access_token_secret = models.TextField()
    is_ban = models.BooleanField()
    status = models.CharField(max_length=32)
    usage_policy = models.CharField(max_length=16)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    remark = models.CharField(max_length=255)
    owner = models.ForeignKey(AuthUser, models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'social_poolaccount'


class StatsDailystat(models.Model):
    id = models.BigAutoField(primary_key=True)
    date = models.DateField()
    owner_id = models.IntegerField(blank=True, null=True)
    account_count = models.IntegerField()
    ins = models.IntegerField()
    x = models.IntegerField()
    fb = models.IntegerField()
    post_count = models.IntegerField()
    reply_comment_count = models.IntegerField()
    reply_message_count = models.IntegerField()
    total_impressions = models.IntegerField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'stats_dailystat'
        unique_together = (('date', 'owner_id'),)


class TArticle(models.Model):
    id = models.BigAutoField(primary_key=True)
    platform = models.CharField(max_length=100)
    impression_count = models.IntegerField()
    comment_count = models.IntegerField()
    message_count = models.IntegerField()
    like_count = models.IntegerField()
    click_count = models.IntegerField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(blank=True, null=True)
    article_id = models.CharField(unique=True, max_length=50, db_comment='文章id')
    article_text = models.TextField()
    robot = models.ForeignKey(SocialPoolaccount, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 't_article'


class TArticleComments(models.Model):
    id = models.BigAutoField(primary_key=True)
    comment_id = models.CharField(unique=True, max_length=50, db_comment='评论ID')
    content = models.TextField(blank=True, null=True, db_comment='内容')
    commenter_id = models.CharField(max_length=50, blank=True, null=True, db_comment='评论者ID')
    commenter_nickname = models.CharField(max_length=100, blank=True, null=True, db_comment='评论者昵称')
    reply_to_id = models.CharField(max_length=50, blank=True, null=True, db_comment='回复者id')
    reply_to_nickname = models.CharField(max_length=100, blank=True, null=True, db_comment='回复者昵称')
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    article = models.ForeignKey(TArticle, models.DO_NOTHING, blank=True, null=True, db_comment='文章id或会话id')

    class Meta:
        managed = False
        db_table = 't_article_comments'


class TaskDetails(models.Model):
    id = models.OneToOneField(TArticle, models.DO_NOTHING, db_column='id', primary_key=True)
    article = models.CharField(max_length=50, blank=True, null=True)
    state = models.CharField(max_length=30, blank=True, null=True, db_comment='任务执行状态')
    create_date = models.DateField(blank=True, null=True, db_comment='创建时间')
    update_date = models.DateField(blank=True, null=True, db_comment='更新时间')
    response = models.TextField(blank=True, null=True, db_comment='执行返回文本内容')
    article_id = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'task_details'


class TasksSimpletask(models.Model):
    id = models.BigAutoField(primary_key=True)
    type = models.CharField(max_length=32)
    provider = models.CharField(max_length=32)
    language = models.CharField(max_length=8)
    text = models.TextField()
    mentions = models.JSONField()
    tags = models.JSONField()
    payload = models.JSONField()
    last_status = models.CharField(max_length=16)
    last_run_at = models.DateTimeField(blank=True, null=True)
    last_success = models.BooleanField()
    last_failed = models.BooleanField()
    last_text = models.TextField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    owner = models.ForeignKey(AuthUser, models.DO_NOTHING)
    prompt = models.ForeignKey(PromptsPromptconfig, models.DO_NOTHING, blank=True, null=True)
    task_remark = models.CharField(max_length=255)

    class Meta:
        managed = False
        db_table = 'tasks_simpletask'


class TasksSimpletaskSelectedAccounts(models.Model):
    id = models.BigAutoField(primary_key=True)
    simpletask = models.ForeignKey(TasksSimpletask, models.DO_NOTHING)
    poolaccount = models.ForeignKey(SocialPoolaccount, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'tasks_simpletask_selected_accounts'
        unique_together = (('simpletask', 'poolaccount'),)


class TasksSimpletaskrun(models.Model):
    id = models.BigAutoField(primary_key=True)
    provider = models.CharField(max_length=32)
    type = models.CharField(max_length=32)
    text = models.TextField()
    used_prompt = models.CharField(max_length=200)
    ai_model = models.CharField(max_length=100)
    ai_provider = models.CharField(max_length=50)
    success = models.CharField(max_length=50)
    external_id = models.CharField(max_length=100)
    error_code = models.CharField(max_length=64)
    error_message = models.TextField()
    created_at = models.DateTimeField()
    account = models.ForeignKey(SocialPoolaccount, models.DO_NOTHING, blank=True, null=True)
    owner = models.ForeignKey(AuthUser, models.DO_NOTHING)
    task = models.ForeignKey(TasksSimpletask, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'tasks_simpletaskrun'


class TokenBlacklistBlacklistedtoken(models.Model):
    id = models.BigAutoField(primary_key=True)
    blacklisted_at = models.DateTimeField()
    token = models.OneToOneField('TokenBlacklistOutstandingtoken', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'token_blacklist_blacklistedtoken'


class TokenBlacklistOutstandingtoken(models.Model):
    id = models.BigAutoField(primary_key=True)
    token = models.TextField()
    created_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField()
    user = models.ForeignKey(AuthUser, models.DO_NOTHING, blank=True, null=True)
    jti = models.CharField(unique=True, max_length=255)

    class Meta:
        managed = False
        db_table = 'token_blacklist_outstandingtoken'
