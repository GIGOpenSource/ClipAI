from django.contrib.auth.models import User, Group, Permission
from django.db.models import Q
from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from .serializers import UserSerializer, GroupSerializer, PermissionSerializer, AuditLogSerializer, SetPasswordSerializer, LoginSerializer, RegistrationSerializer
from .permissions import IsStaffUser
from .models import AuditLog
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse
from django.contrib.auth import authenticate, login
from django.middleware.csrf import get_token
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken


@extend_schema_view(
    list=extend_schema(summary='用户列表', description='支持搜索(q)、is_active 过滤、ordering、分页', tags=['用户']),
    retrieve=extend_schema(summary='用户详情', tags=['用户']),
    create=extend_schema(summary='创建用户', tags=['用户']),
    update=extend_schema(summary='更新用户', tags=['用户']),
    partial_update=extend_schema(summary='部分更新用户', tags=['用户']),
    destroy=extend_schema(summary='删除用户', tags=['用户'])
)
class UserViewSet(mixins.ListModelMixin,
                  mixins.RetrieveModelMixin,
                  mixins.CreateModelMixin,
                  mixins.UpdateModelMixin,
                  mixins.DestroyModelMixin,
                  viewsets.GenericViewSet):
    queryset = User.objects.all().order_by('-id')
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsStaffUser]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))
        active = self.request.query_params.get('is_active')
        if active in {'true','false'}:
            qs = qs.filter(is_active=(active=='true'))
        ordering = self.request.query_params.get('ordering')
        if ordering:
            qs = qs.order_by(ordering)
        return qs

    @extend_schema(summary='启用用户', tags=['用户'], responses={200: OpenApiResponse(description='启用成功')})
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active'])
        return Response({'status': 'activated'})

    @extend_schema(summary='禁用用户', tags=['用户'], responses={200: OpenApiResponse(description='禁用成功')})
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=['is_active'])
        return Response({'status': 'deactivated'})

    @extend_schema(summary='重置用户密码', tags=['用户'], request=SetPasswordSerializer, responses={200: OpenApiResponse(description='设置成功')})
    @action(detail=True, methods=['post'])
    def set_password(self, request, pk=None):
        user = self.get_object()
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data['password'])
        user.save(update_fields=['password'])
        return Response({'status': 'password_set'})


@extend_schema_view(
    list=extend_schema(summary='角色列表', tags=['角色']),
    retrieve=extend_schema(summary='角色详情', tags=['角色']),
    create=extend_schema(summary='创建角色', tags=['角色']),
    update=extend_schema(summary='更新角色', tags=['角色']),
    partial_update=extend_schema(summary='部分更新角色', tags=['角色']),
    destroy=extend_schema(summary='删除角色', tags=['角色'])
)
class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all().order_by('name')
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated, IsStaffUser]

    @extend_schema(
        summary='设置角色权限',
        tags=['角色'],
        request={'application/json': {
            'type': 'object',
            'properties': {
                'permission_ids': {'type': 'array', 'items': {'type': 'integer'}}
            },
            'required': ['permission_ids']
        }}
    )
    @action(detail=True, methods=['post'])
    def set_permissions(self, request, pk=None):
        group = self.get_object()
        permission_ids = request.data.get('permission_ids', [])
        if not isinstance(permission_ids, list):
            return Response({'detail': 'permission_ids must be list'}, status=status.HTTP_400_BAD_REQUEST)
        perms = Permission.objects.filter(id__in=permission_ids)
        group.permissions.set(perms)
        return Response({'status': 'permissions_set'})

    @extend_schema(
        summary='设置角色成员',
        tags=['角色'],
        request={'application/json': {
            'type': 'object',
            'properties': {
                'user_ids': {'type': 'array', 'items': {'type': 'integer'}}
            },
            'required': ['user_ids']
        }}
    )
    @action(detail=True, methods=['post'])
    def set_users(self, request, pk=None):
        group = self.get_object()
        user_ids = request.data.get('user_ids', [])
        if not isinstance(user_ids, list):
            return Response({'detail': 'user_ids must be list'}, status=status.HTTP_400_BAD_REQUEST)
        users = User.objects.filter(id__in=user_ids)
        # clear then add (minimal, fast)
        users_to_clear = User.objects.filter(groups=group)
        for u in users_to_clear:
            u.groups.remove(group)
        for u in users:
            u.groups.add(group)
        return Response({'status': 'users_set'})


@extend_schema_view(
    list=extend_schema(summary='权限列表', tags=['权限']),
    retrieve=extend_schema(summary='权限详情', tags=['权限'])
)
class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Permission.objects.select_related('content_type').all().order_by('codename')
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated, IsStaffUser]


@extend_schema_view(
    list=extend_schema(summary='审计日志列表', tags=['审计日志']),
    retrieve=extend_schema(summary='审计日志详情', tags=['审计日志'])
)
class AuditLogViewSet(mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):

    queryset = AuditLog.objects.select_related('actor').all().order_by('-timestamp')
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsStaffUser]

# Create your views here.


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='登录', tags=['认证'], request=LoginSerializer,
                   responses={200: OpenApiResponse(description='登录成功，返回 access/refresh 与用户信息')})
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, username=serializer.validated_data['username'], password=serializer.validated_data['password'])
        if not user:
            return Response({'detail': '用户名或密码错误'}, status=status.HTTP_400_BAD_REQUEST)
        login(request, user)
        if serializer.validated_data.get('remember_me'):
            request.session.set_expiry(1209600)
        else:
            request.session.set_expiry(0)
        csrf_token = get_token(request)
        refresh = RefreshToken.for_user(user)
        return Response({
            'status': 'ok',
            'csrf_token': csrf_token,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data
        })


class RegisterAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='用户注册', tags=['认证'], request=RegistrationSerializer,
                   responses={201: OpenApiResponse(description='注册成功，返回 access/refresh 与用户信息')})
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'status': 'ok',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data
        }, status=201)
