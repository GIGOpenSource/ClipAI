from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse
from accounts.permissions import IsStaffUser, IsOwnerOrAdmin
from .models import AIConfig
from .serializers import AIConfigSerializer


@extend_schema_view(
    list=extend_schema(summary='AI配置列表', tags=['AI配置']),
    retrieve=extend_schema(summary='AI配置详情', tags=['AI配置']),
    create=extend_schema(summary='创建AI配置', tags=['AI配置']),
    update=extend_schema(summary='更新AI配置', tags=['AI配置']),
    partial_update=extend_schema(summary='部分更新AI配置', tags=['AI配置']),
    destroy=extend_schema(summary='删除AI配置', tags=['AI配置'])
)
class AIConfigViewSet(viewsets.ModelViewSet):
    queryset = AIConfig.objects.all().order_by('-created_at')
    serializer_class = AIConfigSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def perform_create(self, serializer):
        user = self.request.user if self.request and self.request.user.is_authenticated else None
        serializer.save(created_by=user)

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user and user.is_authenticated and user.is_staff:
            return qs
        if user and user.is_authenticated:
            return qs.filter(created_by=user)
        return qs.none()


    @extend_schema(summary='获取默认配置', tags=['AI配置'])
    @action(detail=False, methods=['get'])
    def default(self, request):
        config = AIConfig.objects.filter(is_default=True, enabled=True).first()
        if not config:
            config = AIConfig.objects.filter(enabled=True).order_by('-priority', 'name').first()
        if not config:
            return Response({'detail': '未设置默认配置'}, status=404)
        return Response(self.get_serializer(config).data)

    @extend_schema(summary='设为默认', tags=['AI配置'], responses={200: OpenApiResponse(description='设置成功')})
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        config = self.get_object()
        AIConfig.objects.filter(is_default=True).update(is_default=False)
        config.is_default = True
        config.save(update_fields=['is_default'])
        return Response({'status': 'ok'})

    @extend_schema(summary='测试连通性', tags=['AI配置'], responses={200: OpenApiResponse(description='调用成功，仅做参数校验不真实请求')})
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        config = self.get_object()
        # 简化：不真正请求厂商 API，仅检查关键字段
        if config.provider == 'azure_openai' and (not config.base_url or not config.api_version):
            return Response({'detail': 'Azure OpenAI 需要 base_url 和 api_version'}, status=400)
        if not config.api_key:
            return Response({'detail': '缺少 api_key'}, status=400)
        return Response({'status': 'ok'})

# Create your views here.
