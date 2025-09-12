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


# Brief representation for nested follow targets inside ScheduledTask
class FollowTargetBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = FollowTarget
        fields = [
            'id', 'owner', 'provider', 'external_user_id', 'username',
            'display_name', 'note', 'source', 'enabled', 'completed',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields


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
    completed = serializers.SerializerMethodField()
    # Follow 专用字段
    follow_targets = FollowTargetBriefSerializer(many=True, read_only=True)
    follow_target_ids = serializers.PrimaryKeyRelatedField(queryset=FollowTarget.objects.all(), many=True, required=False, write_only=True)
    follow_max_per_run = serializers.IntegerField(required=False, allow_null=True)
    follow_daily_cap = serializers.IntegerField(required=False, allow_null=True)
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
            'payload_template',
            'follow_targets', 'follow_target_ids', 'follow_max_per_run', 'follow_daily_cap',
            'tags', 'created_at', 'updated_at', 'completed'
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
        # 规范化 provider，避免大小写造成的筛选失配
        attrs['provider'] = provider
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

        # 绑定 social_config_id 的有效性校验：必须存在且 provider 匹配；普通用户必须与任务 owner 相同
        from social.models import SocialConfig
        cfg_id = attrs.get('social_config_id', getattr(instance, 'social_config_id', None))
        if cfg_id is not None:
            cfg = SocialConfig.objects.filter(id=cfg_id).first()
            ensure(bool(cfg), 'social_config_id 不存在')
            ensure(cfg.provider == provider, 'social_config_id 的平台与任务 provider 不一致')
            try:
                req = self.context.get('request') if isinstance(self.context, dict) else None
                is_staff = bool(req and req.user and req.user.is_authenticated and req.user.is_staff)
                # 创建时 owner 可能尚未注入，这里以请求用户校验；管理员放行
                if not is_staff and req and req.user and req.user.is_authenticated:
                    ensure(cfg.owner_id == req.user.id, 'social_config_id 不属于当前用户')
            except Exception:
                pass

        return attrs

    def get_completed(self, obj: ScheduledTask) -> bool:
        try:
            if (getattr(obj, 'type', '') or '').lower() != 'follow':
                return False
            provider = (getattr(obj, 'provider', '') or '').lower()
            if provider != 'twitter':
                return False
            # 优先按显式绑定的 follow_targets 判定
            try:
                bound_qs = getattr(obj, 'follow_targets').all()
                if bound_qs.exists():
                    return not bound_qs.filter(completed=False).exists()
            except Exception:
                pass
            # 否则按租户+平台下是否还有待处理目标
            return not FollowTarget.objects.filter(owner=obj.owner, provider='twitter', enabled=True, completed=False).exists()
        except Exception:
            return False

    def create(self, validated_data):
        follow_target_ids = validated_data.pop('follow_target_ids', None)
        # 当普通用户未显式传 ai_config_id 时，自动选择默认 AIConfig
        try:
            req = self.context.get('request') if isinstance(self.context, dict) else None
            is_staff = bool(req and req.user and req.user.is_authenticated and req.user.is_staff)
            has_ai_cfg = bool(validated_data.get('ai_config_id'))
            if not has_ai_cfg:
                qs = AIConfig.objects.filter(enabled=True)
                cfg = qs.filter(is_default=True).first() or qs.order_by('-priority', 'name').first()
                if cfg and not is_staff:
                    validated_data['ai_config_id'] = cfg.id
        except Exception:
            pass
        instance = super().create(validated_data)
        try:
            if follow_target_ids is not None:
                instance.follow_targets.set(follow_target_ids)
        except Exception:
            pass
        return instance

    def update(self, instance, validated_data):
        follow_target_ids = validated_data.pop('follow_target_ids', None)
        instance = super().update(instance, validated_data)
        try:
            if follow_target_ids is not None:
                instance.follow_targets.set(follow_target_ids)
        except Exception:
            pass
        return instance

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
        print('get_social_config', obj.social_config_id)
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
        # 兼容：运营把 @handle/用户名写进 external_user_id 字段
        ext = (attrs.get('external_user_id') if 'external_user_id' in attrs else getattr(getattr(self, 'instance', None) or object(), 'external_user_id', '')) or ''
        uname = (attrs.get('username') if 'username' in attrs else getattr(getattr(self, 'instance', None) or object(), 'username', '')) or ''
        # 统一去除前缀 @
        if isinstance(uname, str) and uname.startswith('@'):
            attrs['username'] = uname.lstrip('@')
        if isinstance(ext, str) and ext:
            # 如果不是纯数字，则视作用户名写错了位置，转移到 username 并清空 external_user_id
            if not str(ext).isdigit():
                attrs['username'] = (attrs.get('username') or ext).lstrip('@')
                attrs['external_user_id'] = ''
        return attrs

    def get_last_status(self, obj: FollowTarget):
        act = obj.actions.order_by('-executed_at').first()
        return getattr(act, 'status', None)

    def get_last_executed_at(self, obj: FollowTarget):
        act = obj.actions.order_by('-executed_at').first()
        return act.executed_at if act else None

