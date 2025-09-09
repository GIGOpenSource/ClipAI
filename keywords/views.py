from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiParameter
from accounts.permissions import IsStaffUser, IsOwnerOrAdmin
from .models import KeywordConfig
from .serializers import KeywordConfigSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from django.contrib.auth import get_user_model


@extend_schema_view(
    list=extend_schema(summary='关键词配置列表', tags=['关键词配置']),
    retrieve=extend_schema(summary='关键词配置详情', tags=['关键词配置']),
    create=extend_schema(summary='创建关键词配置', tags=['关键词配置']),
    update=extend_schema(summary='更新关键词配置', tags=['关键词配置']),
    partial_update=extend_schema(summary='部分更新关键词配置', tags=['关键词配置']),
    destroy=extend_schema(summary='删除关键词配置', tags=['关键词配置'])
)
class KeywordConfigViewSet(viewsets.ModelViewSet):
    queryset = KeywordConfig.objects.all().order_by('-created_at')
    serializer_class = KeywordConfigSerializer
    permission_classes = [IsAuthenticated, IsStaffUser, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        owner_id = self.request.query_params.get('owner_id')
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            # 管理员：仅当显式传 owner_id 时过滤
            if owner_id:
                qs = qs.filter(owner_id=owner_id)
        else:
            # 非管理员：默认过滤到当前用户
            owner_id = owner_id or (self.request.user.id if self.request.user.is_authenticated else None)
            if owner_id:
                qs = qs.filter(owner_id=owner_id)
        provider = self.request.query_params.get('provider')
        if provider:
            qs = qs.filter(provider=provider)
        enabled = self.request.query_params.get('enabled')
        if enabled in {'true', 'false'}:
            qs = qs.filter(enabled=(enabled == 'true'))
        return qs

    def perform_create(self, serializer):
        if self.request.user and self.request.user.is_authenticated:
            serializer.save(owner=self.request.user)
        else:
            serializer.save()

    @extend_schema(
        summary='管理员为指定 owner 创建关键词配置',
        description='仅管理员可用；请求体与普通创建一致，额外支持 owner_id 指定归属用户',
        tags=['关键词配置'],
        parameters=[OpenApiParameter(name='owner_id', description='目标用户ID', required=True, type=int)],
        responses={200: OpenApiResponse(description='创建成功')}
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsStaffUser])
    def admin_create(self, request):
        owner_id = request.query_params.get('owner_id') or request.data.get('owner_id')
        if not owner_id:
            return Response({'detail': '缺少 owner_id'}, status=400)
        try:
            owner = get_user_model().objects.get(id=owner_id)
        except get_user_model().DoesNotExist:
            return Response({'detail': 'owner 不存在'}, status=404)
        payload = request.data.copy()
        payload['owner'] = owner.id
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        serializer.save(owner=owner)
        return Response(serializer.data, status=201)


# Create your views here.
