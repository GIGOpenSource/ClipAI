from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import SocialConfig


class SocialConfigSerializer(serializers.ModelSerializer):
    # 掩码字段
    client_secret_masked = serializers.SerializerMethodField()
    bearer_token_masked = serializers.SerializerMethodField()
    app_secret_masked = serializers.SerializerMethodField()
    page_access_token_masked = serializers.SerializerMethodField()
    # 所有者详情（只读）
    class OwnerBriefSerializer(serializers.ModelSerializer):
        class Meta:
            model = get_user_model()
            fields = ['id', 'username', 'email', 'first_name', 'last_name']

    owner_detail = OwnerBriefSerializer(source='owner', read_only=True)

    class Meta:
        model = SocialConfig
        fields = [
            'id', 'provider', 'name', 'enabled', 'is_default', 'priority', 'owner', 'owner_detail',
            'client_id', 'client_secret', 'client_secret_masked',
            'api_version', 'redirect_uris', 'scopes',
            'bearer_token', 'bearer_token_masked',
            'app_id', 'app_secret', 'app_secret_masked',
            'page_id', 'page_access_token', 'page_access_token_masked',
            'ig_business_account_id', 'webhook_verify_token', 'signing_secret',
            'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']
        extra_kwargs = {
            'client_secret': {'write_only': True},
            'bearer_token': {'write_only': True},
            'app_secret': {'write_only': True},
            'page_access_token': {'write_only': True},
        }

    def _mask(self, value: str) -> str:
        if not value:
            return ''
        return f"***{value[-4:]}"

    def get_client_secret_masked(self, obj):
        return self._mask(obj.client_secret)

    def get_bearer_token_masked(self, obj):
        return self._mask(obj.bearer_token)

    def get_app_secret_masked(self, obj):
        return self._mask(obj.app_secret)

    def get_page_access_token_masked(self, obj):
        return self._mask(obj.page_access_token)

    def validate(self, attrs):
        provider = attrs.get('provider', getattr(self.instance, 'provider', None))
        # 平台必填校验
        if provider == 'twitter':
            for key in ['client_id', 'client_secret']:
                if not attrs.get(key) and not (self.instance and getattr(self.instance, key)):
                    raise serializers.ValidationError(f'Twitter 需要 {key}')
        if provider == 'facebook':
            for key in ['app_id', 'app_secret']:
                if not attrs.get(key) and not (self.instance and getattr(self.instance, key)):
                    raise serializers.ValidationError(f'Facebook 需要 {key}')
        if provider == 'instagram':
            for key in ['app_id', 'app_secret']:
                if not attrs.get(key) and not (self.instance and getattr(self.instance, key)):
                    raise serializers.ValidationError(f'Instagram 需要 {key}')
        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        # 如果未显式传 owner，则默认归属当前操作用户
        if 'owner' not in validated_data and request and request.user.is_authenticated:
            validated_data['owner'] = request.user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # 未传密钥则保留原值
        for key in ['client_secret', 'bearer_token', 'app_secret', 'page_access_token']:
            if key not in validated_data:
                validated_data[key] = getattr(instance, key)
        return super().update(instance, validated_data)


