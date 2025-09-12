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
from stats.utils import record_success_run


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
        summary='一键配置 Twitter 关注（创建/更新 FollowTarget + 创建/更新 ScheduledTask）',
        description=(
            """
除立即执行外，将关注目标与任务调度整合为单一接口；原有接口保持不变。仅支持 provider=twitter，type=follow。

请求示例：
{
  "owner_id": 1,              // 管理员可指定；普通用户忽略
  "targets": [                 // 可选：批量增改关注目标
    {"external_user_id":"123", "username":"elonmusk", "enabled":true, "runner_account_ids":[5,6]}
  ],
  "task": {                    // 必填：创建或更新调度任务
    "id": null,               // 传 id 则更新；不传则创建
    "recurrence_type":"hourly", "interval_value":1, "enabled":true,
    "payload_template": {"max_per_run":5, "daily_cap":30},
    "social_config_id": null, "keyword_config_id": null, "prompt_config_id": null
  }
}
            """
        ),
        tags=['任务调度'],
        responses={200: OpenApiResponse(description='已完成配置，返回任务与统计结果')}
    )
    @action(detail=False, methods=['post'], url_path='scheduled/setup-follow')
    def setup_follow(self, request):
        user = request.user
        if not (user and user.is_authenticated):
            return Response({'detail': '未登录'}, status=401)

        body = request.data if hasattr(request, 'data') else {}
        # 选择 owner：普通用户强制为自己；管理员可通过 owner_id 指定
        owner_obj = user
        if user.is_staff:
            try:
                owner_id = body.get('owner_id')
                if owner_id:
                    from django.contrib.auth import get_user_model
                    owner_obj = get_user_model().objects.filter(id=owner_id).first() or user
            except Exception:
                owner_obj = user
        # 1) 批量 upsert 关注目标（可选）
        targets = body.get('targets') or []
        created_targets = []
        updated_targets = []
        errors = []
        for idx, t in enumerate(targets):
            try:
                provider = 'twitter'
                ext_id = (t or {}).get('external_user_id')
                if not ext_id:
                    raise ValueError('external_user_id 必填')
                defaults = {
                    'username': (t or {}).get('username') or '',
                    'display_name': (t or {}).get('display_name') or '',
                    'note': (t or {}).get('note') or '',
                    'source': (t or {}).get('source') or 'manual',
                    'enabled': bool((t or {}).get('enabled', True)),
                }
                obj, created = FollowTarget.objects.update_or_create(
                    owner=owner_obj,
                    provider=provider,
                    external_user_id=str(ext_id),
                    defaults=defaults
                )
                # 绑定 runner_accounts（可选）
                try:
                    acc_ids = (t or {}).get('runner_account_ids') or []
                    if isinstance(acc_ids, list):
                        qs = SocialAccount.objects.filter(id__in=acc_ids, provider='twitter')
                        obj.runner_accounts.set(list(qs))
                except Exception:
                    pass
                (created_targets if created else updated_targets).append(obj.id)
            except Exception as e:
                errors.append({'index': idx, 'error': str(e)})

        # 2) 创建/更新 ScheduledTask（type=follow, provider=twitter）
        task_payload = body.get('task') or {}
        task_id = task_payload.get('id')
        task_payload = dict(task_payload)
        task_payload['type'] = 'follow'
        task_payload['provider'] = 'twitter'
        instance = None
        if task_id:
            instance = ScheduledTask.objects.filter(id=task_id, owner=owner_obj, type='follow', provider='twitter').first()
            if not instance:
                return Response({'detail': '任务不存在或无权限'}, status=404)
        # 使用 Serializer 校验与保存
        serializer_ctx = {'request': request}
        if instance:
            ser = ScheduledTaskSerializer(instance, data=task_payload, partial=True, context=serializer_ctx)
        else:
            ser = ScheduledTaskSerializer(data=task_payload, context=serializer_ctx)
        if ser.is_valid():
            if instance:
                scheduled = ser.save()
            else:
                # 普通用户强制归属自己；管理员创建时使用 owner_obj
                scheduled = ser.save(owner=owner_obj)
        else:
            return Response({'detail': '任务参数校验失败', 'errors': ser.errors}, status=400)

        resp_data = {
            'owner_id': owner_obj.id,
            'scheduled_task': ScheduledTaskSerializer(scheduled).data,
            'targets': {
                'created_ids': created_targets,
                'updated_ids': updated_targets,
                'errors': errors,
            }
        }
        return Response(resp_data)

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

        # Increment lightweight daily stat on success (simple rule): one success = +1
        try:
            if run.success:
                record_success_run(owner_id=run.owner_id, provider=run.provider, task_type=run.task_type, started_date=run.started_at.date())
        except Exception:
            pass
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

    def destroy(self, request, *args, **kwargs):
        # 仅管理员可删除标签
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            return Response({'detail': '仅管理员可删除标签'}, status=403)
        return super().destroy(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        # 仅管理员可更新标签
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            return Response({'detail': '仅管理员可更新标签'}, status=403)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        # 仅管理员可部分更新标签
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            return Response({'detail': '仅管理员可更新标签'}, status=403)
        return super().partial_update(request, *args, **kwargs)


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
                qs = qs.filter(owner_id=user.id)
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
        # 规则：未传 owner_id 默认使用自己的 user_id；管理员若传 owner_id 则按传入，否则也用自己的
        owner_id = self.request.query_params.get('owner_id')
        if user and user.is_authenticated:
            if user.is_staff and owner_id:
                try:
                    from django.contrib.auth import get_user_model
                    owner_obj = get_user_model().objects.filter(id=owner_id).first()
                    if owner_obj:
                        serializer.save(owner=owner_obj)
                        return
                except Exception:
                    pass
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
