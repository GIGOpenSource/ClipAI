from django.utils import timezone
from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiParameter
from accounts.permissions import IsStaffUser, IsOwnerOrAdmin
from .models import ScheduledTask, TaskRun, Tag, FollowTarget
from .serializers import ScheduledTaskSerializer, TaskRunSerializer, TagSerializer, FollowTargetSerializer
from .tasks import execute_scheduled_task
from .runner import execute_task, generate_ai_preview
from .clients import TwitterClient
from social.models import SocialAccount


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
        # Persist last external id if provided (for downstream monitoring)
        try:
            last_ext_id = data.get('agg', {}).get('last_external_id')
            if last_ext_id:
                run.external_object_id = str(last_ext_id)
                run.save(update_fields=['external_object_id'])
        except Exception:
            pass
        run.finished_at = timezone.now()
        run.save(update_fields=['finished_at'])
        task.last_run_at = run.finished_at
        task.save(update_fields=['last_run_at'])
        # Create SocialPost record on successful publish
        try:
            from .models import SocialPost
            payload = resp or {}
            provider = data['agg']['provider']
            ext_id = None
            text_used = (task.payload_template or {}).get('text', '')
            if provider == 'twitter' and isinstance(payload.get('tweet'), dict):
                ext_id = ((payload.get('tweet') or {}).get('data') or {}).get('id')
                text_used = ((payload.get('tweet') or {}).get('data') or {}).get('text') or text_used
            elif provider == 'facebook' and isinstance(payload.get('facebook_post'), dict):
                ext_id = (payload.get('facebook_post') or {}).get('id')
            elif provider == 'instagram' and isinstance(payload.get('ig_media'), dict):
                ext_id = (payload.get('ig_media') or {}).get('id')
            if ext_id:
                SocialPost.objects.create(
                    owner=task.owner,
                    provider=provider,
                    scheduled_task=task,
                    task_run=run,
                    external_id=str(ext_id),
                    text=text_used or '',
                    payload=payload,
                )
        except Exception:
            pass
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

class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all().order_by('name')
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(name__icontains=q)
        return qs

    def perform_create(self, serializer):
        # 普通用户允许创建标签（全局共享），如需限制可改为管理员专属
        serializer.save()


class FollowTargetViewSet(viewsets.ModelViewSet):
    queryset = FollowTarget.objects.all().order_by('-updated_at')
    serializer_class = FollowTargetSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user and user.is_authenticated and user.is_staff:
            owner_id = self.request.query_params.get('owner_id')
            if owner_id:
                qs = qs.filter(owner_id=owner_id)
        else:
            uid = user.id if user and user.is_authenticated else None
            qs = qs.filter(owner_id=uid) if uid else qs.none()
        provider = self.request.query_params.get('provider')
        if provider:
            qs = qs.filter(provider=provider.lower())
        enabled = self.request.query_params.get('enabled')
        if enabled in {'true','false'}:
            qs = qs.filter(enabled=(enabled=='true'))
        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(username__icontains=q)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if user and user.is_authenticated and not user.is_staff:
            serializer.save(owner=user)
        else:
            serializer.save()

    @extend_schema(summary='从 Twitter 同步“我正在关注的人”到 FollowTarget（默认不启用）', tags=['关注'] )
    @action(detail=False, methods=['post'], url_path='sync/twitter')
    def sync_twitter(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({'detail': '未登录'}, status=401)
        # 选择当前租户最近的 Twitter 账号
        account = SocialAccount.objects.filter(owner_id=user.id, provider='twitter', status='active').order_by('-updated_at').first()
        if not account:
            return Response({'detail': '未绑定 Twitter 账号'}, status=400)
        bearer = account.get_access_token() or None
        consumer_key = None
        consumer_secret = None
        access_token = None
        access_token_secret = None
        # 如无 OAuth2，尝试 OAuth1
        if not bearer:
            access_token = account.get_access_token()
            access_token_secret = account.get_refresh_token()
        cli = None
        if bearer:
            cli = TwitterClient(bearer_token=bearer)
        elif access_token and access_token_secret:
            # 客户端内部会以 OAuth1 会话发起请求
            from social.models import SocialConfig
            cfg = SocialConfig.objects.filter(provider='twitter', owner_id=user.id).order_by('-is_default', '-priority').first()
            if cfg and cfg.client_id and cfg.client_secret:
                consumer_key = cfg.client_id
                consumer_secret = cfg.client_secret
            cli = TwitterClient(consumer_key=consumer_key, consumer_secret=consumer_secret,
                                access_token=access_token, access_token_secret=access_token_secret)
        if not cli:
            return Response({'detail': '缺少有效的 Twitter 凭据'}, status=400)
        # 获取自身 user id
        try:
            me = cli.get_me()
        except Exception as e:
            return Response({'detail': '获取用户信息失败', 'error': str(e)}, status=400)
        uid = ((me or {}).get('data') or {}).get('id') or (me or {}).get('id')
        if not uid:
            return Response({'detail': '无法识别用户ID'}, status=400)
        # 分页拉取 following 列表
        saved = 0
        token = None
        for _ in range(10):  # 最多翻10页，避免超量
            try:
                page = cli.get_following(uid, pagination_token=token, max_results=100)
            except Exception as e:
                return Response({'detail': '拉取关注列表失败', 'error': str(e)}, status=400)
            data = (page or {}).get('data') or []
            meta = (page or {}).get('meta') or {}
            for u in data:
                ext_id = u.get('id') or ''
                username = u.get('username') or ''
                name = u.get('name') or ''
                if not ext_id:
                    continue
                FollowTarget.objects.update_or_create(
                    owner=user,
                    provider='twitter',
                    external_user_id=ext_id,
                    defaults={'username': username, 'display_name': name, 'source': 'imported', 'enabled': False}
                )
                saved += 1
            token = meta.get('next_token')
            if not token:
                break
        return Response({'status': 'ok', 'synced': saved})
