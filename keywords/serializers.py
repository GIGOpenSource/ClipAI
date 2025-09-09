from rest_framework import serializers
from .models import KeywordConfig
from django.contrib.auth import get_user_model


class KeywordConfigSerializer(serializers.ModelSerializer):
    class OwnerBriefSerializer(serializers.ModelSerializer):
        class Meta:
            model = get_user_model()
            fields = ['id', 'username', 'email', 'first_name', 'last_name']

    owner_detail = OwnerBriefSerializer(source='owner', read_only=True)

    class Meta:
        model = KeywordConfig
        fields = [
            'id', 'owner', 'owner_detail', 'name', 'provider', 'include_keywords', 'exclude_keywords', 'match_mode', 'enabled',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def _ensure_list_of_str(self, value):
        if value in (None, ''):
            return []
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError('关键词需为字符串数组')
        return value

    def validate(self, attrs):
        mode = attrs.get('match_mode', getattr(self.instance, 'match_mode', 'any'))
        include_keywords = self._ensure_list_of_str(attrs.get('include_keywords', getattr(self.instance, 'include_keywords', [])))
        exclude_keywords = self._ensure_list_of_str(attrs.get('exclude_keywords', getattr(self.instance, 'exclude_keywords', [])))
        if mode not in {'any', 'all', 'regex'}:
            raise serializers.ValidationError('match_mode 仅支持 any/all/regex')
        # 简单正则合法性检查（不阻断保存，仅保证至少一个合法）
        if mode == 'regex' and include_keywords:
            import re
            try:
                for p in include_keywords:
                    re.compile(p)
            except re.error:
                raise serializers.ValidationError('include_keywords 含非法正则')
        attrs['include_keywords'] = include_keywords
        attrs['exclude_keywords'] = exclude_keywords
        return attrs


