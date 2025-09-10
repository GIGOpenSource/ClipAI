from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ScheduledTask, TaskRun, Tag, TagTemplate
from social.models import SocialConfig
from ai.models import AIConfig
from keywords.models import KeywordConfig
from prompts.models import PromptConfig


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
    tag_template = serializers.PrimaryKeyRelatedField(queryset=TagTemplate.objects.all(), required=False, allow_null=True)
    tag_template_detail = serializers.SerializerMethodField()
    class Meta:
        model = ScheduledTask
        fields = [
            'id', 'owner', 'owner_detail', 'type', 'provider',
            'social_config_id', 'ai_config_id', 'keyword_config_id', 'prompt_config_id',
            'social_config', 'ai_config', 'keyword_config', 'prompt_config',
            'recurrence_type', 'interval_value', 'time_of_day', 'weekday_mask', 'day_of_month', 'timezone', 'start_at', 'end_at', 'cron_expr',
            'enabled',
            'next_run_at', 'last_run_at', 'status', 'max_retries', 'rate_limit_hint',
            'payload_template', 'tags', 'tag_template', 'tag_template_detail', 'created_at', 'updated_at'
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

        return attrs

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

    def get_tag_template_detail(self, obj):
        tpl = getattr(obj, 'tag_template', None)
        if not tpl:
            return None
        return {
            'id': tpl.id,
            'name': tpl.name,
            'owner': tpl.owner_id,
            'tags': [t.id for t in tpl.tags.all()],
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        tpl = attrs.get('tag_template', getattr(self.instance, 'tag_template', None))
        if tpl and user and user.is_authenticated and not user.is_staff:
            if tpl.owner_id != user.id:
                raise serializers.ValidationError('只能选择你自己的标签模板')
        return attrs


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


class TagTemplateSerializer(serializers.ModelSerializer):
    class OwnerBriefSerializer(serializers.ModelSerializer):
        class Meta:
            model = get_user_model()
            fields = ['id', 'username']
    owner_detail = OwnerBriefSerializer(source='owner', read_only=True)
    tags = serializers.PrimaryKeyRelatedField(queryset=Tag.objects.all(), many=True, required=False)

    class Meta:
        model = TagTemplate
        fields = ['id', 'name', 'owner', 'owner_detail', 'tags', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def create(self, validated_data):
        tags = validated_data.pop('tags', [])
        inst = super().create(validated_data)
        if tags:
            inst.tags.set(tags)
        return inst

    def update(self, instance, validated_data):
        tags = validated_data.pop('tags', None)
        inst = super().update(instance, validated_data)
        if tags is not None:
            inst.tags.set(tags)
        return inst


