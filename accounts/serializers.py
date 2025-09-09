from django.contrib.auth.models import Permission, Group, User
from rest_framework import serializers
from .models import AuditLog


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        min_length=6,
        max_length=128,
        help_text='初始密码，至少 6 位（仅创建时使用，不会出现在返回中）'
    )

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'is_active', 'is_staff', 'is_superuser', 'date_joined', 'last_login', 'password']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        # 忽略密码更新（请使用专门的重置密码接口）
        validated_data.pop('password', None)
        return super().update(instance, validated_data)


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=6, max_length=128, help_text='新密码，至少 6 位')


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(help_text='管理员用户名')
    password = serializers.CharField(write_only=True, help_text='密码')
    remember_me = serializers.BooleanField(required=False, default=False, help_text='记住登录（两周）')


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id', 'codename', 'name', 'content_type']


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'actor', 'actor_username', 'action', 'target_type', 'target_id',
            'timestamp', 'ip_address', 'user_agent', 'success', 'metadata'
        ]


class RegistrationSerializer(serializers.Serializer):
    username = serializers.CharField(min_length=3, max_length=150)
    password = serializers.CharField(write_only=True, min_length=6, max_length=128)
    email = serializers.EmailField(required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('用户名已存在')
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data.get('email', ''),
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        return user

