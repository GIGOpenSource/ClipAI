from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ScheduledTask, TaskRun, Tag, FollowTarget, FollowAction
from social.models import SocialConfig, SocialAccount
from ai.models import AIConfig
from keywords.models import KeywordConfig
from prompts.models import PromptConfig

DEFAULT_PAYLOAD_TEXTS = {
    'post': '请生成一条适合平台的中文发帖文案。',
    'reply_comment': '请针对该评论给出简短友好回复。',
    'reply_message': '请针对该消息给出简短友好回复。',
    'follow': '关注目标账户。'
}


class ScheduledTaskSerializer(serializers.ModelSerializer):
    class OwnerBriefSerializer(serializers.ModelSerializer):
        class Meta:
            model = get_user_model()
            fields = ['id', 'username', 'email', 'first_name', 'last_name']

    owner_detail = OwnerBriefSerializer(source='owner', read_only=True)
    social_config = serializers.SerializerMethodField()
    ai_config = serializers.SerializerMethodField()
    keyword_config = serializers.SerializerMethodField()
    prompt_config = serializers.SerializerMethodField()
    tags = serializers.PrimaryKeyRelatedField(queryset=Tag.objects.all(), many=True, required=False)
    # 移除任务级 runner_accounts（转移到 FollowTarget）
    class Meta:
        model = ScheduledTask
        fields = [
            'id', 'owner', 'owner_detail', 'type', 'provider',
            'social_config_id', 'ai_config_id', 'keyword_config_id', 'prompt_config_id',
            'social_config', 'ai_config', 'keyword_config', 'prompt_config',
            'recurrence_type', 'interval_value', 'time_of_day', 'weekday_mask', 'day_of_month', 'timezone', 'start_at', 'end_at', 'cron_expr',
            'enabled',
            'next_run_at', 'last_run_at', 'status', 'max_retries', 'rate_limit_hint',
            'payload_template', 'tags', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        recurrence_type = attrs.get('recurrence_type', getattr(instance, 'recurrence_type', 'once'))
        interval_value = attrs.get('interval_value', getattr(instance, 'interval_value', None))
        time_of_day = attrs.get('time_of_day', getattr(instance, 'time_of_day', None))
        weekday_mask = attrs.get('weekday_mask', getattr(instance, 'weekday_mask', [])) or []
        day_of_month = attrs.get('day_of_month', getattr(instance, 'day_of_month', None))
        cron_expr = attrs.get('cron_expr', getattr(instance, 'cron_expr', '')) or ''
        provider = (attrs.get('provider') or getattr(instance, 'provider', '') or '').lower()
        task_type = attrs.get('type', getattr(instance, 'type', ''))

        def ensure(cond: bool, msg: str):
            if not cond:
                raise serializers.ValidationError(msg)

        if recurrence_type in {'minutely', 'hourly'}:
            ensure(isinstance(interval_value, int) and interval_value > 0, 'interval_value 必须为正整数（minutely/hourly）')
        if recurrence_type in {'daily', 'weekly', 'monthly'}:
            ensure(bool(time_of_day), 'time_of_day 为必填（daily/weekly/monthly）')
        if recurrence_type == 'weekly':
            allowed = {'mon','tue','wed','thu','fri','sat','sun'}
            ensure(isinstance(weekday_mask, list) and weekday_mask and set(weekday_mask).issubset(allowed), 'weekday_mask 必须为 {mon..sun} 非空子集（weekly）')
        if recurrence_type == 'monthly':
            ensure(isinstance(day_of_month, int) and (-31 <= day_of_month <= -1 or 1 <= day_of_month <= 31), 'day_of_month 必须在 [-31,-1] 或 [1,31]（monthly）')
        if recurrence_type == 'cron':
            parts = [p for p in cron_expr.strip().split() if p]
            ensure(5 <= len(parts) <= 6, 'cron_expr 非法，应为 5 或 6 段表达式')

        # 业务约束：关注任务仅支持 Twitter
        if task_type == 'follow':
            ensure(provider == 'twitter', '关注任务目前仅支持 Twitter 平台')

        # 业务约束：Instagram 发帖必须包含媒体 URL（image_url 或 video_url）
        if provider == 'instagram' and task_type == 'post':
            payload = attrs.get('payload_template', getattr(instance, 'payload_template', {})) or {}
            has_media = bool(payload.get('image_url') or payload.get('video_url'))
            ensure(has_media, 'Instagram 发帖需要提供 image_url 或 video_url')

        # 不再接收任务级 runner_accounts

        # payload_template.text 默认值（按任务类型）
        payload = attrs.get('payload_template', getattr(instance, 'payload_template', {})) or {}
        if not isinstance(payload, dict):
            payload = {}
        txt = (payload.get('text') or '').strip()
        if not txt:
            default_text = DEFAULT_PAYLOAD_TEXTS.get(task_type)
            if default_text is not None:
                payload['text'] = default_text
        attrs['payload_template'] = payload

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            if (getattr(instance, 'type', '') or '') != 'follow':
                # 非关注任务不展示 runner_accounts 字段
                data.pop('runner_accounts', None)
        except Exception:
            pass
        return data

    def _as_dict(self, obj, fields):
        return {k: getattr(obj, k) for k in fields}

    def get_social_config(self, obj):
        if not obj.social_config_id:
            return None
        cfg = SocialConfig.objects.filter(id=obj.social_config_id).first()
        if not cfg:
            return None
        return {
            'id': cfg.id,
            'name': cfg.name,
            'provider': cfg.provider,
            'owner': cfg.owner_id,
        }

    def get_ai_config(self, obj):
        if not obj.ai_config_id:
            return None
        cfg = AIConfig.objects.filter(id=obj.ai_config_id).first()
        if not cfg:
            return None
        return {
            'id': cfg.id,
            'name': cfg.name,
            'provider': cfg.provider,
            'model': cfg.model,
        }

    def get_keyword_config(self, obj):
        if not obj.keyword_config_id:
            return None
        cfg = KeywordConfig.objects.filter(id=obj.keyword_config_id).first()
        if not cfg:
            return None
        return {
            'id': cfg.id,
            'owner': cfg.owner_id,
            'name': cfg.name,
            'provider': cfg.provider,
            'match_mode': cfg.match_mode,
            'enabled': cfg.enabled,
        }

    def get_prompt_config(self, obj):
        if not obj.prompt_config_id:
            return None
        cfg = PromptConfig.objects.filter(id=obj.prompt_config_id).first()
        if not cfg:
            return None
        return {
            'id': cfg.id,
            'owner': cfg.owner_id,
            'scene': cfg.scene,
            'name': cfg.name,
            'enabled': cfg.enabled,
        }


class TaskRunSerializer(serializers.ModelSerializer):
    scheduled_task_detail = ScheduledTaskSerializer(source='scheduled_task', read_only=True)
    class OwnerBriefSerializer(serializers.ModelSerializer):
        class Meta:
            model = get_user_model()
            fields = ['id', 'username', 'email', 'first_name', 'last_name']
    owner_detail = OwnerBriefSerializer(source='scheduled_task.owner', read_only=True)
    class Meta:
        model = TaskRun
        fields = [
            'id', 'scheduled_task', 'scheduled_task_detail', 'owner_detail',
            'started_at', 'finished_at', 'status', 'error',
            'request_dump', 'response_dump', 'affected_ids'
        ]
        read_only_fields = fields


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['created_at']


class FollowTargetSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    provider = serializers.CharField(required=False, default='twitter')
    class OwnerBriefSerializer(serializers.ModelSerializer):
        class Meta:
            model = get_user_model()
            fields = ['id', 'username']
    owner_detail = OwnerBriefSerializer(source='owner', read_only=True)
    last_status = serializers.SerializerMethodField()
    last_executed_at = serializers.SerializerMethodField()
    runner_accounts = serializers.PrimaryKeyRelatedField(queryset=SocialAccount.objects.all(), many=True, required=False)

    class Meta:
        model = FollowTarget
        fields = [
            'id', 'owner', 'owner_detail', 'provider', 'external_user_id', 'username',
            'display_name', 'note', 'source', 'enabled', 'completed', 'created_at', 'updated_at',
            'last_status', 'last_executed_at', 'runner_accounts'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 所有人都可以选择任意 Twitter 账号（不限制状态）
        try:
            self.fields['runner_accounts'].queryset = SocialAccount.objects.filter(provider='twitter')
        except Exception:
            pass

    def validate(self, attrs):
        request = self.context.get('request') if isinstance(self.context, dict) else None
        provider = (attrs.get('provider') or getattr(getattr(self, 'instance', None) or object(), 'provider', None) or 'twitter').lower()
        attrs['provider'] = provider
        if provider != 'twitter':
            raise serializers.ValidationError('关注目标目前仅支持 twitter')
        return attrs

    def get_last_status(self, obj: FollowTarget):
        act = obj.actions.order_by('-executed_at').first()
        return getattr(act, 'status', None)

    def get_last_executed_at(self, obj: FollowTarget):
        act = obj.actions.order_by('-executed_at').first()
        return act.executed_at if act else None

