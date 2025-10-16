from django.contrib.messages.context_processors import messages
from django.db.models import Max
from drf_spectacular.types import OpenApiTypes
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiParameter
from urllib3 import request

from accounts.permissions import IsOwnerOrAdmin
from models.models import TasksSimpletaskrun, TasksSimpletask
from utils.utils import logger, ApiResponse, CustomPagination, generate_message, merge_text
from .models import SimpleTask, SimpleTaskRun
from .serializers import SimpleTaskSerializer, SimpleTaskRunSerializer, SimpleTaskRunDetailSerializer
from stats.utils import record_success_run
from django.utils import timezone
from ai.models import AIConfig
from social.models import PoolAccount
from utils.largeModelUnit import LargeModelUnit
from utils.twitterUnit import TwitterUnit, createTaskDetail
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend


@extend_schema(tags=["任务日志"])
@extend_schema_view(
    list=extend_schema(summary='任务日志列表',
                       parameters=[OpenApiParameter(name='start_date', description='开始日期 (格式: YYYY-MM-DD)',
                                                    required=False, type=OpenApiTypes.DATE),
                                   OpenApiParameter(name='end_date', description='结束日期 (格式: YYYY-MM-DD)',
                                                    required=False, type=OpenApiTypes.DATE),
                                   ]),
)
class SimpleTaskRunViewSet(viewsets.ModelViewSet):
    serializer_class = SimpleTaskRunSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['provider', 'type', 'prompt__id']
    search_fields = ['text']
    ordering_fields = ['created_at']

    def list(self, request, *args, **kwargs):
        # 获取过滤后的查询集
        queryset = self.filter_queryset(self.get_queryset())
        # 获取分页器实例
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            # 使用自定义分页响应
            return self.get_paginated_response(serializer.data)
        # 如果没有分页，返回普通响应
        serializer = self.get_serializer(queryset, many=True)
        return ApiResponse(serializer.data)

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return TasksSimpletask.objects.none()
        # 获取用户有权限访问的任务运行记录
        if user.is_staff:
            task_runs = TasksSimpletaskrun.objects.all()
        else:
            task_runs = TasksSimpletaskrun.objects.filter(owner=user)
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            try:
                from datetime import datetime
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                task_runs = task_runs.filter(created_at__date__gte=start_date_obj)
            except ValueError:
                print("日期格式错误")
                pass  # 如果日期格式错误，忽略过滤
        if end_date:
            try:
                from datetime import datetime
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                task_runs = task_runs.filter(created_at__date__lte=end_date_obj)
            except ValueError:
                print("日期格式错误")
                pass
                # 按 task_id 分组，获取每个任务的最新运行时间
        latest_runs = task_runs.values('task_id').annotate(
            latest_run_time=Max('created_at')
        ).order_by('-latest_run_time')
        # 提取 task_id 列表
        task_ids = [item['task_id'] for item in latest_runs]
        # 根据 task_ids 查询 TasksSimpletask 表
        if user.is_staff:
            queryset = TasksSimpletask.objects.filter(id__in=task_ids)
        else:
            queryset = TasksSimpletask.objects.filter(id__in=task_ids, owner=user)
        return queryset.order_by('-created_at')


from rest_framework.views import APIView


class TaskLogView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='任务日志详情',
        tags=['任务日志'],
        responses=OpenApiTypes.OBJECT,
        parameters=[
            OpenApiParameter(
                name='simpletask_id',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='任务ID',
                required=True
            ),
            OpenApiParameter(
                name='status',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='状态 success/failed',
                required=False
            ), OpenApiParameter(
                name='currentPage',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='当前页码',
                required=False
            ),
            OpenApiParameter(
                name='pageSize',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description='每页条数',
                required=False
            ),
        ]
    )
    def get(self, request):
        simpletask_id = request.query_params.get('simpletask_id')
        status = request.query_params.get('status')
        user = self.request.user
        if user.is_staff:
            queryset = TasksSimpletaskrun.objects.all()
        else:
            queryset = TasksSimpletaskrun.objects.filter(owner=request.user)
        if simpletask_id:
            try:
                queryset = queryset.filter(task_id=int(simpletask_id))
            except (ValueError, TypeError):
                return ApiResponse({'error': '无效的任务ID'}, status=400)

        if status:
            queryset = queryset.filter(success=status)
        queryset = queryset.order_by('-created_at')
        # serializer = SimpleTaskRunDetailSerializer(queryset, many=True)
        # return ApiResponse(serializer.data)
        paginator = CustomPagination()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = SimpleTaskRunDetailSerializer(paginated_queryset, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        summary='重试失败任务',
        tags=['任务日志'],
        responses=OpenApiTypes.OBJECT,
        parameters=[
            OpenApiParameter(
                name='simpletask_id',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='任务ID',
                required=True
            ),
        ]
    )
    def post(self, request):
        simpletask_id = request.query_params.get('simpletask_id')
        user = request.user
        if not simpletask_id:
            return ApiResponse({'error': '任务ID是必需的'}, status=400)
        # 获取指定任务中失败的运行记录
        if user.is_staff:
            failed_runs = TasksSimpletaskrun.objects.filter(
                task_id=int(simpletask_id),
                success='failed'  # 根据实际数据库存储格式调整
            )
        else:
            failed_runs = TasksSimpletaskrun.objects.filter(
                task_id=int(simpletask_id),
                success='failed',  # 根据实际数据库存储格式调整
                owner=user
            )
        # 返回失败的任务ID列表
        failed_ids = list(failed_runs.values_list('id', flat=True))
        return ApiResponse({
            'message': f'找到 {len(failed_ids)} 个失败的任务',
            'failed_task_ids': failed_ids
        })


@extend_schema(tags=["任务执行（定时/非定时）"])
@extend_schema_view(
    list=extend_schema(summary='简单任务列表'),
    retrieve=extend_schema(summary='简单任务详情'),
    create=extend_schema(summary='创建简单任务（非定时）'),
    update=extend_schema(summary='更新简单任务'),

    partial_update=extend_schema(summary='部分更新简单任务'),
    destroy=extend_schema(summary='删除简单任务')
)
class SimpleTaskViewSet(viewsets.ModelViewSet):
    queryset = SimpleTask.objects.all().order_by('-created_at')
    serializer_class = SimpleTaskSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.select_related('prompt', 'owner').prefetch_related('selected_accounts')

        if not (self.request.user and self.request.user.is_authenticated and self.request.user.is_staff):
            qs = qs.filter(owner=self.request.user)
        provider = self.request.query_params.get('provider')
        if provider:
            qs = qs.filter(provider=provider)
        return qs

    @extend_schema(
        summary='立即执行简单任务（并行多账号）',
        description='根据 selected_accounts 逐个账号执行。AI 文案按优先级回退。',
        responses={200: OpenApiResponse(description='执行完成，返回每账号结果')}
    )
    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        task = self.get_object()
        # Helper: extract HTTP status code from exceptions
        def _extract_status_code(exc):
            try:
                resp = getattr(exc, 'response', None)
                if resp is not None:
                    return getattr(resp, 'status_code', None) or getattr(resp, 'status', None)
            except Exception:
                return None
            return None

        # Helper: mark account status by code
        def _mark_account_by_code(acc: PoolAccount, code: int | None):
            try:
                if code in (401, 403):
                    acc.is_ban = True
                    acc.status = 'banned'
                    acc.save(update_fields=['is_ban', 'status'])
                elif code == 429 or (code and 500 <= int(code) <= 599):
                    acc.status = 'warn'
                    acc.save(update_fields=['status'])
                elif code:
                    acc.status = 'unknown'
                    acc.save(update_fields=['status'])
            except Exception:
                pass

        # 获取 AI 配置（在循环外部获取一次）
        ai_qs = AIConfig.objects.filter(enabled=True).order_by('-priority', 'name')

        try:
            selected_qs = task.selected_accounts.all()
            selected_ids = list(selected_qs.values_list('id', flat=True))
        except Exception as e:
            return Response({
                'detail': '获取选中账户时出错',
                'error': str(e),
                'selected_account_ids': list(task.selected_accounts.values_list('id', flat=True))
            }, status=400)

        # 运行前：将所选账号设为激活
        if selected_ids:
            try:
                PoolAccount.objects.filter(id__in=selected_ids).update(status='active')
            except Exception:
                pass
        # 平台执行
        results = []
        ok_count = 0
        err_count = 0
        for acc in selected_qs:
            user_text = (task.text or '').strip()
            text = ''
            ai_meta = {}
            last_err = None
            # 每日使用上限：limited 账号每天最多使用 2 次（无论成功与否）
            try:
                if getattr(acc, 'usage_policy', 'unlimited') == 'limited':
                    today = timezone.now().date()
                    used_today = SimpleTaskRun.objects.filter(account=acc, created_at__date=today).count()
                    if used_today >= 2:
                        results.append({'account_id': acc.id, 'status': 'skipped', 'reason': 'daily_limit_reached',
                                        'used_today': used_today})
                        continue
            except Exception:
                pass
            should_generate_content = True  # 或者根据具体条件判断
            if should_generate_content:
                for cfg in ai_qs:
                    try:
                        cli = LargeModelUnit(cfg.model, cfg.api_key, cfg.base_url)
                        messages = generate_message(task)
                        if user_text:
                            messages.append({'role': 'user', 'content': f"补充上下文：{user_text}"})
                        logger.info(f"为账号 {acc.id} 调用 chat_completion")
                        if cfg.provider == "openai":
                            flag, text = cli.generateToOpenAI(messages=messages)
                        if cfg.provider == "deepseek":
                            flag, text = cli.generateToDeepSeek(messages=messages)
                        if flag:
                            ai_meta = {
                                'model': cfg.model,
                                'provider': cfg.provider,
                                # 'latency_ms': res.get('latency_ms'),
                                # 'tokens': res.get('tokens'),
                                # 'used_prompt': getattr(task.prompt, 'name', None),
                                'final_text': text,
                                'language': getattr(task, 'language', 'auto'),
                            }
                            break
                    except Exception as e:
                        last_err = str(e)
                        logger.info(f"为账号 {acc.id} 调用模型失败：{last_err}")

            # 如果没有生成文本但有用户文本，使用用户文本
            if not text and user_text:
                text = user_text
                ai_meta = {
                    'model': 'user_provided',
                    'provider': 'user',
                    # 'latency_ms': 0,
                    # 'tokens': 0,
                    # 'used_prompt': None,
                    'final_text': text,
                    'language': getattr(task, 'language', 'auto'),
                }
            # 如果仍然没有文本，跳过该账号
            if not text:
                results.append(
                    {'account_id': acc.id, 'status': 'skipped', 'reason': 'no_content_generated', 'error': last_err})
                err_count += 1
                continue

            # 附加 tags/mentions（mentions 前缀 @）
            final_text = text  # 使用为当前账号生成的文本
            logger.info(f"为账号 {acc.id} 生成的文本：{final_text}")
            final_text = merge_text(task, final_text)
            try:
                if task.provider == 'twitter':
                    api_key = acc.api_key
                    api_secret = acc.api_secret
                    at = acc.get_access_token()
                    ats = acc.get_access_token_secret()
                    client = TwitterUnit(api_key, api_secret, at, ats)
                    if task.type == 'post':
                        flag, resp = client.sendTwitter(final_text, int(acc.id), task, cfg, userId=self.request.user.id)
                        logger.info(f"推文发送成功响应: {resp}")
                        """
                        {'edit_history_tweet_ids': ['1976839557380554887'], 'id': '1976839557380554887', 'text': '测试'}
                        """
                        if flag:
                            tweet_id = resp["id"]
                            results.append(
                                {'account_id': acc.id, 'status': 'ok', 'tweet_id': tweet_id,
                                 'account_status': acc.status})
                            ok_count += 1
                        else:
                            tweet_id = ""
                            err_count += 1

                        try:
                            record_success_run(owner_id=task.owner_id, provider='twitter', task_type=task.type,
                                               started_date=timezone.now().date())
                        except Exception:
                            pass
            #     elif task.provider == 'facebook':
            #         # 官方 Graph API（使用 requests 或 facebook-sdk；此处直接调用 Graph endpoint 简化）
            #         import requests
            #         page_token = acc.get_access_token()
            #         page_id = (task.payload or {}).get('page_id')
            #         if not page_token or not page_id:
            #             results.append(
            #                 {'account_id': acc.id, 'status': 'skipped', 'reason': 'missing_page_token_or_page_id'})
            #             continue
            #         base = 'https://graph.facebook.com/v19.0'
            #         if task.type == 'post':
            #             r = requests.post(f"{base}/{page_id}/feed",
            #                               data={'message': final_text, 'access_token': page_token}, timeout=20)
            #             r.raise_for_status()
            #             body = r.json()
            #             results.append(
            #                 {'account_id': acc.id, 'status': 'ok', 'post': body, 'account_status': acc.status})
            #             ok_count += 1
            #             try:
            #                 SimpleTaskRun.objects.create(
            #                     task=task, owner_id=task.owner_id, provider='facebook', type='post',
            #                     account=acc, text=final_text, used_prompt=(getattr(task.prompt, 'name', '') or ''),
            #                     ai_model=(ai_meta.get('model') if isinstance(ai_meta, dict) else '') or '',
            #                     ai_provider=(ai_meta.get('provider') if isinstance(ai_meta, dict) else '') or '',
            #                     success=True, external_id=str((body.get('id') if isinstance(body, dict) else '') or ''),
            #                     error_code='', error_message='',
            #                 )
            #             except Exception:
            #                 pass
            #             try:
            #                 record_success_run(owner_id=task.owner_id, provider='facebook', task_type='post',
            #                                    started_date=timezone.now().date())
            #             except Exception:
            #                 pass
            #         elif task.type == 'reply_comment':
            #             cid = (task.payload or {}).get('comment_id')
            #             if not cid:
            #                 results.append({'account_id': acc.id, 'status': 'skipped', 'reason': 'missing_comment_id'})
            #                 continue
            #             r = requests.post(f"{base}/{cid}/comments",
            #                               data={'message': final_text, 'access_token': page_token}, timeout=20)
            #             r.raise_for_status()
            #             body = r.json()
            #             results.append(
            #                 {'account_id': acc.id, 'status': 'ok', 'reply': body, 'account_status': acc.status})
            #             ok_count += 1
            #             try:
            #                 SimpleTaskRun.objects.create(
            #                     task=task, owner_id=task.owner_id, provider='facebook', type='reply_comment',
            #                     account=acc, text=final_text, used_prompt=(getattr(task.prompt, 'name', '') or ''),
            #                     ai_model=(ai_meta.get('model') if isinstance(ai_meta, dict) else '') or '',
            #                     ai_provider=(ai_meta.get('provider') if isinstance(ai_meta, dict) else '') or '',
            #                     success=True, external_id=str((body.get('id') if isinstance(body, dict) else '') or ''),
            #                     error_code='', error_message='',
            #                 )
            #             except Exception:
            #                 pass
            #             try:
            #                 record_success_run(owner_id=task.owner_id, provider='facebook', task_type='reply_comment',
            #                                    started_date=timezone.now().date())
            #             except Exception:
            #                 pass
            #     else:
            #         results.append({'account_id': acc.id, 'status': 'skipped', 'reason': 'unsupported_provider'})
            except Exception as e:
                code = _extract_status_code(e)
                try:
                    _mark_account_by_code(acc, code)
                except Exception:
                    pass
                results.append({'account_id': acc.id, 'status': 'error', 'error': str(e), 'code': code,
                                'account_status': acc.status})
                err_count += 1
                createTaskDetail(task.provider, text=final_text, sendType=task.type, task=task, aiConfig=cfg,
                                 status=False, errorMessage=str(e), userId=self.request.user.id, robotId=acc.id,
                                 articleId=None)
        # 运行完成：将仍为 active 的账号改回 inactive
        if selected_ids:
            try:
                PoolAccount.objects.filter(id__in=selected_ids, status='active').update(status='inactive')
            except Exception:
                pass
        # 汇总并写回任务状态
        try:
            from django.utils import timezone as _tz
            if ok_count and not err_count:
                task.last_status = 'success'
                task.last_success = True
                task.last_failed = False
            elif ok_count and err_count:
                task.last_status = 'partial'
                task.last_success = False
                task.last_failed = True
            else:
                task.last_status = 'error'
                task.last_success = False
                task.last_failed = True
            task.last_run_at = _tz.now()
            task.save(update_fields=['last_status', 'last_success', 'last_failed', 'last_run_at'])
        except Exception:
            pass
        return Response({'status': 'ok', 'summary': {'ok': ok_count, 'error': err_count}, 'results': results})


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


class TaskTagsView(APIView):
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get(self, request, task_id):
        """
        获取指定任务的标签列表
        """
        try:
            task = SimpleTask.objects.get(id=task_id)
            # 检查权限
            if not (request.user.is_staff or task.owner == request.user):
                return Response({'detail': '权限不足'}, status=status.HTTP_403_FORBIDDEN)

            return Response({
                'task_id': task.id,
                'tags': task.tags
            })
        except SimpleTask.DoesNotExist:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, task_id):
        """
        为指定任务添加标签
        """
        try:
            task = SimpleTask.objects.get(id=task_id)
            # 检查权限
            if not (request.user.is_staff or task.owner == request.user):
                return Response({'detail': '权限不足'}, status=status.HTTP_403_FORBIDDEN)

            tag_name = request.data.get('name')
            if not tag_name:
                return Response({'detail': 'name 字段是必需的'}, status=status.HTTP_400_BAD_REQUEST)

            # 确保 tags 是列表
            if not isinstance(task.tags, list):
                task.tags = []

            # 避免重复添加
            if tag_name not in task.tags:
                task.tags.append(tag_name)
                task.save(update_fields=['tags'])

            return Response({
                'task_id': task.id,
                'tags': task.tags,
                'message': f'标签 "{tag_name}" 已添加'
            }, status=status.HTTP_201_CREATED)

        except SimpleTask.DoesNotExist:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, task_id):
        """
        删除指定任务的标签
        """
        try:
            task = SimpleTask.objects.get(id=task_id)
            # 检查权限
            if not (request.user.is_staff or task.owner == request.user):
                return Response({'detail': '权限不足'}, status=status.HTTP_403_FORBIDDEN)

            tag_name = request.data.get('name')
            if not tag_name:
                return Response({'detail': 'name 字段是必需的'}, status=status.HTTP_400_BAD_REQUEST)

            # 确保 tags 是列表
            if not isinstance(task.tags, list):
                task.tags = []

            # 删除标签
            if tag_name in task.tags:
                task.tags.remove(tag_name)
                task.save(update_fields=['tags'])
                message = f'标签 "{tag_name}" 已删除'
            else:
                message = f'标签 "{tag_name}" 不存在'

            return Response({
                'task_id': task.id,
                'tags': task.tags,
                'message': message
            })

        except SimpleTask.DoesNotExist:
            return Response({'detail': '任务不存在'}, status=status.HTTP_404_NOT_FOUND)


class GlobalTagsView(APIView):
    """
    全局标签操作视图（获取所有任务中使用的标签）
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        获取当前用户所有任务中的标签列表
        """
        try:
            # 获取当前用户的所有任务
            if request.user.is_staff:
                tasks = SimpleTask.objects.all()
            else:
                tasks = SimpleTask.objects.filter(owner=request.user)

            # 收集所有唯一标签
            all_tags = set()
            for task in tasks:
                if isinstance(task.tags, list):
                    all_tags.update(task.tags)

            return Response({
                'tags': list(all_tags),
                'count': len(all_tags)
            })
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from django.http import JsonResponse

from datetime import datetime


class TaskSchedulerView(APIView):
    """配置定时任务的接口"""

    @extend_schema(
        summary='创建每日定时任务',
        tags=['定时任务'],
        description='创建一个每天指定时间执行的定时任务',
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'hour': {
                        'type': 'integer',
                        'description': '执行小时 (0-23)',
                        'example': 10
                    },
                    'minute': {
                        'type': 'integer',
                        'description': '执行分钟 (0-59)',
                        'example': 30
                    },
                    'repeat_times': {
                        'type': 'integer',
                        'description': '每次执行的重复次数',
                        'example': 3
                    }
                },
                'required': ['hour']
            }
        },
        responses={
            200: {
                'description': '任务创建成功',
                'content': {
                    'application/json': {
                        'example': {
                            'status': 'success',
                            'message': '定时任务已配置'
                        }
                    }
                }
            },
            400: {
                'description': '请求参数错误',
                'content': {
                    'application/json': {
                        'example': {
                            'status': 'error',
                            'message': '错误信息'
                        }
                    }
                }
            }
        }
    )
    def post(self, request):
        # 示例：配置每天10:30执行3次任务
        try:
            hour = request.data.get('hour', 10)
            minute = request.data.get('minute', 30)
            repeat_times = request.data.get('repeat_times', 3)

            # 调用autoTask中的方法创建定时任务
            # schedule_daily_task(hour=hour, minute=minute, repeat_times=repeat_times)
            return JsonResponse({'status': 'success', 'message': '定时任务已配置'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# def scheduler_test():
#     print('定时任务触发')
#
# from apscheduler.schedulers.background import BackgroundScheduler
# scheduler = BackgroundScheduler()
# try:
#     # 添加定时任务，第一个参数为需要定时执行的任务，'cron'定时任务类型，每天0点，30分执行一次，任务id为test。
# 	scheduler.add_job(scheduler_test, 'cron', hour=11, minute=35, id='test', replace_existing=True,timezone='Asia/Shanghai')
#     # 启动定时任务
# 	scheduler.start()
# except Exception as e:
#     print(e)
#     # 停止定时任务
#     scheduler.shutdown()
