from rest_framework import serializers
from .models import PoolAccount
class PoolAccountSerializer(serializers.ModelSerializer):
    api_secret = serializers.CharField(required=False, allow_blank=True)
    access_token = serializers.CharField(required=False, allow_blank=True)
    access_token_secret = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = PoolAccount
        fields = [
            'id', 'provider', 'name', 'api_key', 'api_secret',
            'access_token', 'access_token_secret', 'is_ban', 'status', 'usage_policy',
            'remark','created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at','owner']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # 不回显敏感密钥，仅回显掩码
        def _mask(val: str | None):
            if not val:
                return ''
            return f"***{val[-4:]}" if len(val) >= 4 else '***'
        data['api_key_masked'] = _mask(getattr(instance, 'api_key', ''))
        return data

    def create(self, validated_data):
        owner = validated_data.pop('owner', None)
        acc = PoolAccount(
            provider=validated_data.get('provider'),
            name=validated_data.get('name'),
            api_key=validated_data.get('api_key', ''),
            api_secret=validated_data.get('api_secret', ''),
            is_ban=validated_data.get('is_ban', False),
            status=validated_data.get('status', 'active'),
            remark=validated_data.get('remark', ''),
            usage_policy=validated_data.get('usage_policy', 'unlimited'),
            owner=owner
        )
        if 'access_token' in validated_data:
            acc.set_access_token(validated_data.get('access_token'))
        if 'access_token_secret' in validated_data:
            acc.set_access_token_secret(validated_data.get('access_token_secret'))
        acc.save()
        return acc

    def update(self, instance, validated_data):
        owner = validated_data.pop('owner', None)
        if owner is not None:
            instance.owner = owner
        for f in ['provider', 'name', 'api_key', 'api_secret', 'is_ban', 'status','remark', 'usage_policy']:
            if f in validated_data:
                setattr(instance, f, validated_data.get(f))
        if 'access_token' in validated_data:
            instance.set_access_token(validated_data.get('access_token'))
        if 'access_token_secret' in validated_data:
            instance.set_access_token_secret(validated_data.get('access_token_secret'))
        instance.save()
        return instance

