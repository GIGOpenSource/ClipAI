from rest_framework import serializers
from .models import PromptConfig
from django.contrib.auth import get_user_model


class PromptConfigSerializer(serializers.ModelSerializer):
    # owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    owner = serializers.PrimaryKeyRelatedField(
        queryset=get_user_model().objects.all(),  # 关联 User 模型的查询集
        write_only=True,  # 仅用于接收/修改，不返回给前端（前端用 owner_detail 看详情）
        required=False,  # 非必填：未传时默认用当前用户
        default=serializers.CurrentUserDefault()  # 默认值：当前登录用户
    )
    owner_id = serializers.IntegerField(
        write_only=True,  # 仅接收，不返回
        required=False,  # 非必填：未传时用 owner 的默认值
        allow_null=True  # 允许传 null（表示用默认用户）
    )

    class OwnerBriefSerializer(serializers.ModelSerializer):
        class Meta:
            model = get_user_model()
            fields = ['id', 'username', 'email', 'first_name', 'last_name']

    owner_detail = OwnerBriefSerializer(source='owner', read_only=True)

    class Meta:
        model = PromptConfig
        fields = [
            'id', 'owner', 'owner_id','owner_detail', 'scene', 'name', 'content', 'variables', 'enabled', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def validate_variables(self, value):
        if value in (None, ''):
            return []
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError('variables 必须为字符串数组')
        return value

    def validate(self, attrs):
        owner_id = attrs.pop('owner_id', None)
        current_user = self.context['request'].user if 'request' in self.context else None
        if owner_id is not None:
            try:
                # 查询对应的用户（必须存在）
                target_owner = get_user_model().objects.get(id=owner_id)
                # 将查询到的 User 对象赋值给 owner（覆盖默认的 current_user）
                attrs['owner'] = target_owner
            except get_user_model().DoesNotExist:
                raise serializers.ValidationError({'owner_id': '指定的 owner_id 不存在'})
        final_owner = attrs.get('owner')
        if current_user and not current_user.is_staff:  # is_staff 表示管理员（django 内置字段）
            if final_owner != current_user:
                raise serializers.ValidationError({'owner_id': '非管理员无法设置他人为所有者'})
        enabled = attrs.get('enabled', getattr(self.instance, 'enabled', True))
        content = attrs.get('content', getattr(self.instance, 'content', ''))
        if enabled and not content:
            raise serializers.ValidationError('启用状态下 content 必填')
        # 权限检查：只有管理员可以设置其他用户为所有者
        if enabled and not content:
            raise serializers.ValidationError('启用状态下 content 必填')
        return attrs


