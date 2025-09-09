from rest_framework import serializers
from .models import PromptConfig
from django.contrib.auth import get_user_model


class PromptConfigSerializer(serializers.ModelSerializer):
    class OwnerBriefSerializer(serializers.ModelSerializer):
        class Meta:
            model = get_user_model()
            fields = ['id', 'username', 'email', 'first_name', 'last_name']

    owner_detail = OwnerBriefSerializer(source='owner', read_only=True)

    class Meta:
        model = PromptConfig
        fields = [
            'id', 'owner', 'owner_detail', 'scene', 'name', 'content', 'variables', 'enabled', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_variables(self, value):
        if value in (None, ''):
            return []
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError('variables 必须为字符串数组')
        return value

    def validate(self, attrs):
        enabled = attrs.get('enabled', getattr(self.instance, 'enabled', True))
        content = attrs.get('content', getattr(self.instance, 'content', ''))
        if enabled and not content:
            raise serializers.ValidationError('启用状态下 content 必填')
        return attrs


