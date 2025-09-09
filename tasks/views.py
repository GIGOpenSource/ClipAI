from django.utils import timezone
from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiParameter
from accounts.permissions import IsStaffUser, IsOwnerOrAdmin
from .models import ScheduledTask, TaskRun
from .serializers import ScheduledTaskSerializer, TaskRunSerializer
from .tasks import execute_scheduled_task
from .runner import execute_task, generate_ai_preview


@extend_schema_view(
    list=extend_schema(summary='任务列表', tags=['任务调度']),
    retrieve=extend_schema(summary='任务详情', tags=['任务调度']),
    create=extend_schema(summary='创建任务（建议填写 interval_minutes，schedule 为高级可选）', tags=['任务调度']),
    update=extend_schema(summary='更新任务（建议填写 interval_minutes）', tags=['任务调度']),
    partial_update=extend_schema(summary='部分更新任务（建议填写 interval_minutes）', tags=['任务调度']),
    destroy=extend_schema(summary='删除任务', tags=['任务调度'])
)
class ScheduledTaskViewSet(viewsets.ModelViewSet):
    queryset = ScheduledTask.objects.all().order_by('-created_at')
    serializer_class = ScheduledTaskSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            owner_id = self.request.query_params.get('owner_id')
            if owner_id:
                qs = qs.filter(owner_id=owner_id)
        else:
            owner_id = self.request.user.id if self.request.user and self.request.user.is_authenticated else None
            qs = qs.filter(owner_id=owner_id) if owner_id else qs.none()
        provider = self.request.query_params.get('provider')
        if provider:
            qs = qs.filter(provider=provider)
        return qs

    def perform_create(self, serializer):
        # 普通用户仅能创建自己的任务；管理员可指定 owner
        if self.request.user and self.request.user.is_authenticated and not self.request.user.is_staff:
            serializer.save(owner=self.request.user)
        else:
            serializer.save()

    @extend_schema(
        summary='立即执行任务（支持预览）',
        description='mode=preview 时仅生成 AI 文本，不外呼、不写入 TaskRun；否则执行真实/回退流程',
        tags=['任务调度'],
        parameters=[
            OpenApiParameter(name='mode', description='预览模式：preview', required=False, type=str)
        ],
        responses={200: OpenApiResponse(description='执行完成或返回预览')}
    )
    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        task = self.get_object()
        # 预览模式：仅生成 AI 文本，不外呼
        if request.query_params.get('mode') == 'preview':
            preview = generate_ai_preview(task)
            return Response({'mode': 'preview', **preview})
        # 允许通过请求体临时覆盖 payload_template（不保存到数据库），便于避免幂等冲突或做瞬时验证
        try:
            body = request.data if hasattr(request, 'data') else None
            if isinstance(body, dict) and 'payload_template' in body:
                task.payload_template = body.get('payload_template')
        except Exception:
            pass
        data = execute_task(task)
        resp = data.get('response', {}) or {}
        ai_meta = resp.get('ai_meta', {})
        rl_hit = bool(resp.get('rate_limit_warning') or (resp.get('skipped') == 'rate_limited'))
        run = TaskRun.objects.create(
            scheduled_task=task,
            status='succeeded',
            request_dump=data['request_dump'],
            response_dump=data['response'],
            success=data['agg']['success'],
            duration_ms=data['agg']['duration_ms'],
            owner_id=data['agg']['owner_id'],
            provider=data['agg']['provider'],
            task_type=data['agg']['task_type'],
            social_config_id_used=data['used']['social_config_id_used'],
            ai_config_id_used=data['used']['ai_config_id_used'],
            keyword_config_id_used=data['used']['keyword_config_id_used'],
            prompt_config_id_used=data['used']['prompt_config_id_used'],
            sla_met=data['agg']['sla_met'],
            rate_limit_hit=rl_hit,
            ai_model=ai_meta.get('model') or '',
            ai_tokens=ai_meta.get('tokens') or None,
            ai_latency_ms=ai_meta.get('latency_ms') or None
        )
        run.finished_at = timezone.now()
        run.save(update_fields=['finished_at'])
        task.last_run_at = run.finished_at
        task.save(update_fields=['last_run_at'])
        return Response(TaskRunSerializer(run).data)

    @extend_schema(summary='异步执行任务（Celery）', tags=['任务调度'])
    @action(detail=True, methods=['post'])
    def run_async(self, request, pk=None):
        task = self.get_object()
        execute_scheduled_task.delay(task.id)
        return Response({'status': 'queued'})


class TaskRunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = TaskRun.objects.select_related('scheduled_task').all()
    serializer_class = TaskRunSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        # 仅返回本人任务的运行（非管理员）
        if not (self.request.user and self.request.user.is_authenticated and self.request.user.is_staff):
            qs = qs.filter(owner_id=self.request.user.id if self.request.user and self.request.user.is_authenticated else -1)
        task_id = self.request.query_params.get('task_id')
        if task_id:
            qs = qs.filter(scheduled_task_id=task_id)
        return qs

# Create your views here.
