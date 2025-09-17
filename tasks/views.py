from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse
from accounts.permissions import IsOwnerOrAdmin
from .models import SimpleTask, SimpleTaskRun
from .serializers import SimpleTaskSerializer
from stats.utils import record_success_run
from django.utils import timezone


@extend_schema_view(
    list=extend_schema(summary='简单任务列表', tags=['任务执行（非定时）']),
    retrieve=extend_schema(summary='简单任务详情', tags=['任务执行（非定时）']),
    create=extend_schema(summary='创建简单任务（非定时）', tags=['任务执行（非定时）']),
    update=extend_schema(summary='更新简单任务', tags=['任务执行（非定时）']),
    partial_update=extend_schema(summary='部分更新简单任务', tags=['任务执行（非定时）']),
    destroy=extend_schema(summary='删除简单任务', tags=['任务执行（非定时）'])
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
        tags=['任务执行（非定时）'],
        responses={200: OpenApiResponse(description='执行完成，返回每账号结果')}
    )
    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        task = self.get_object()
        from ai.models import AIConfig
        from ai.client import OpenAICompatibleClient
        from social.models import PoolAccount
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
        # 生成文本：总是尝试用 AI 生成；若用户给了 text，将其作为上下文提示
        user_text = (task.text or '').strip()
        text = ''
        ai_meta = {}
        ai_qs = AIConfig.objects.filter(enabled=True).order_by('-priority', 'name')
        last_err = None
        # Map language code to display name for clearer instruction
        lang_map = {
            'auto': 'Auto',
            'zh': 'Chinese',
            'en': 'English',
            'ja': 'Japanese',
            'ko': 'Korean',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
        }
        lang_code = (getattr(task, 'language', 'auto') or 'auto')
        lang_name = lang_map.get(lang_code, 'Auto')
        for cfg in ai_qs:
            try:
                # cli = OpenAI(base_url=cfg.base_url or 'https://api.openai.com', api_key=cfg.api_key)
                cli = OpenAICompatibleClient(base_url=cfg.base_url or 'https://api.openai.com', api_key=cfg.api_key)
                # Build system and user prompts per language
                if lang_code == 'en':
                    base_sys = 'You are a social media copywriter. Generate concise, safe English content suitable for Twitter.'
                    messages = [
                        {'role': 'system', 'content': base_sys},
                        {'role': 'system', 'content': 'Target language: English. Reply ONLY in English. Keep it short and friendly.'},
                        {'role': 'user', 'content': f"Please write a short post for {task.provider}."},
                    ]
                elif lang_code == 'zh' or lang_code == 'auto':
                    base_sys = (getattr(task.prompt, 'content', None) or '你是一个社交媒体助理，请生成简短中文内容。')
                    messages = [
                        {'role': 'system', 'content': base_sys},
                        {'role': 'user', 'content': f"请生成适合 {task.provider} 的{ '回复评论' if task.type=='reply_comment' else '发帖'}文案。"},
                    ]
                else:
                    base_sys = f'You are a social media copywriter. Generate concise, safe {lang_name} content suitable for Twitter.'
                    messages = [
                        {'role': 'system', 'content': base_sys},
                        {'role': 'system', 'content': f"Target language: {lang_name}. Reply ONLY in {lang_name}. Keep it short and friendly."},
                        {'role': 'user', 'content': f"Please write a short post for {task.provider}."},
                    ]
                if user_text:
                    messages.append({'role': 'user', 'content': f"补充上下文：{user_text}"})
                res = cli.chat_completion(model=cfg.model, messages=messages)
                text = (res.get('content') or '').strip()
                if text:
                    ai_meta = {
                        'model': cfg.model,
                        'provider': cfg.provider,
                        'latency_ms': res.get('latency_ms'),
                        'tokens': res.get('tokens'),
                        'used_prompt': getattr(task.prompt, 'name', None),
                        'final_text': text,
                        'language': getattr(task, 'language', 'auto'),
                    }
                    break
            except Exception as e:
                last_err = str(e)
                print("模型访问失败：",last_err)
        if not text:
            return Response({'detail': 'AI 生成失败（AI 为必需）', 'error': last_err or 'no text generated'}, status=400)
        # 附加 tags/mentions（mentions 前缀 @）
        if task.tags:
            tail = ' ' + ' '.join('#' + t.lstrip('#') for t in task.tags[:5])
            text = (text + tail).strip()
        if task.mentions:
            # mstr = ' ' + ' '.join('@' + str(m).lstrip('@') for m in task.mentions[:10])
            # text = (text + mstr).strip()
            # 处理 mentions：支持字符串和列表格式
            mention_list = []
            if isinstance(task.mentions, str):
                # 字符串格式：'user1,user2,user3'
                mention_list = [m.strip() for m in task.mentions.split(',') if m.strip()]
            elif isinstance(task.mentions, list):
                # 列表格式：['user1', 'user2', 'user3']
                mention_list = [str(m).strip() for m in task.mentions if str(m).strip()]
            # 添加 @ 符号前缀并限制数量
            if mention_list:
                mstr = ' ' + ' '.join('@' + m.lstrip('@') for m in mention_list[:10])
                text = (text + mstr).strip()

        # 平台执行
        results = []
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
        ok_count = 0
        err_count = 0
        for acc in selected_qs:
            # 每日使用上限：limited 账号每天最多使用 2 次（无论成功与否）
            try:
                if getattr(acc, 'usage_policy', 'unlimited') == 'limited':
                    today = timezone.now().date()
                    used_today = SimpleTaskRun.objects.filter(account=acc, created_at__date=today).count()
                    if used_today >= 2:
                        results.append({'account_id': acc.id, 'status': 'skipped', 'reason': 'daily_limit_reached', 'used_today': used_today})
                        continue
            except Exception:
                pass
            try:
                if task.provider == 'twitter':
                    # 官方库 Tweepy，使用 OAuth1.0a
                    import tweepy
                    api_key = acc.api_key
                    api_secret = acc.api_secret
                    at = acc.get_access_token()
                    ats = acc.get_access_token_secret()
                    client = tweepy.Client(
                        consumer_key=api_key,
                        consumer_secret=api_secret,
                        access_token=at,
                        access_token_secret=ats
                    )
                    if task.type == 'post':
                        resp = client.create_tweet(text=text)
                        print(f"推文发送成功响应: {resp}")
                        tweet_id = None
                        try:
                            data = getattr(resp, 'data', None) or {}
                            tweet_id = data.get('id') if isinstance(data, dict) else getattr(data, 'id', None)
                        except Exception:
                            tweet_id = None
                        results.append({'account_id': acc.id, 'status': 'ok', 'tweet_id': tweet_id, 'account_status': acc.status})
                        ok_count += 1
                        try:
                            SimpleTaskRun.objects.create(
                                task=task, owner_id=task.owner_id, provider='twitter', type=task.type,
                                account=acc, text=text, used_prompt=(getattr(task.prompt, 'name', '') or ''),
                                ai_model=(ai_meta.get('model') if isinstance(ai_meta, dict) else '') or '',
                                ai_provider=(ai_meta.get('provider') if isinstance(ai_meta, dict) else '') or '',
                                success=True, external_id=str(tweet_id or ''), error_code='', error_message='',
                            )

                        except Exception:
                            pass
                        try:
                            record_success_run(owner_id=task.owner_id, provider='twitter', task_type=task.type, started_date=timezone.now().date())
                        except Exception:
                            pass
                    elif task.type == 'reply_comment':
                        cid = (task.payload or {}).get('comment_id')
                        if not cid:
                            results.append({'account_id': acc.id, 'status': 'skipped', 'reason': 'missing_comment_id'})
                            continue
                        resp = client.create_tweet(text=text, reply={'in_reply_to_tweet_id': cid})
                        reply_id = None
                        try:
                            data = getattr(resp, 'data', None) or {}
                            reply_id = data.get('id') if isinstance(data, dict) else getattr(data, 'id', None)
                        except Exception:
                            reply_id = None
                        results.append({'account_id': acc.id, 'status': 'ok', 'reply_id': reply_id, 'account_status': acc.status})
                        ok_count += 1
                        try:
                            SimpleTaskRun.objects.create(
                                task=task, owner_id=task.owner_id, provider='twitter', type=task.type,
                                account=acc, text=text, used_prompt=(getattr(task.prompt, 'name', '') or ''),
                                ai_model=(ai_meta.get('model') if isinstance(ai_meta, dict) else '') or '',
                                ai_provider=(ai_meta.get('provider') if isinstance(ai_meta, dict) else '') or '',
                                success=True, external_id=str(reply_id or ''), error_code='', error_message='',
                            )
                        except Exception:
                            pass
                        try:
                            record_success_run(owner_id=task.owner_id, provider='twitter', task_type=task.type, started_date=timezone.now().date())
                        except Exception:
                            pass
                elif task.provider == 'facebook':
                    # 官方 Graph API（使用 requests 或 facebook-sdk；此处直接调用 Graph endpoint 简化）
                    import requests
                    page_token = acc.get_access_token()
                    page_id = (task.payload or {}).get('page_id')
                    if not page_token or not page_id:
                        results.append({'account_id': acc.id, 'status': 'skipped', 'reason': 'missing_page_token_or_page_id'})
                        continue
                    base = 'https://graph.facebook.com/v19.0'
                    if task.type == 'post':
                        r = requests.post(f"{base}/{page_id}/feed", data={'message': text, 'access_token': page_token}, timeout=20)
                        r.raise_for_status()
                        body = r.json()
                        results.append({'account_id': acc.id, 'status': 'ok', 'post': body, 'account_status': acc.status})
                        ok_count += 1
                        try:
                            SimpleTaskRun.objects.create(
                                task=task, owner_id=task.owner_id, provider='facebook', type='post',
                                account=acc, text=text, used_prompt=(getattr(task.prompt, 'name', '') or ''),
                                ai_model=(ai_meta.get('model') if isinstance(ai_meta, dict) else '') or '',
                                ai_provider=(ai_meta.get('provider') if isinstance(ai_meta, dict) else '') or '',
                                success=True, external_id=str((body.get('id') if isinstance(body, dict) else '') or ''), error_code='', error_message='',
                            )
                        except Exception:
                            pass
                        try:
                            record_success_run(owner_id=task.owner_id, provider='facebook', task_type='post', started_date=timezone.now().date())
                        except Exception:
                            pass
                    elif task.type == 'reply_comment':
                        cid = (task.payload or {}).get('comment_id')
                        if not cid:
                            results.append({'account_id': acc.id, 'status': 'skipped', 'reason': 'missing_comment_id'})
                            continue
                        r = requests.post(f"{base}/{cid}/comments", data={'message': text, 'access_token': page_token}, timeout=20)
                        r.raise_for_status()
                        body = r.json()
                        results.append({'account_id': acc.id, 'status': 'ok', 'reply': body, 'account_status': acc.status})
                        ok_count += 1
                        try:
                            SimpleTaskRun.objects.create(
                                task=task, owner_id=task.owner_id, provider='facebook', type='reply_comment',
                                account=acc, text=text, used_prompt=(getattr(task.prompt, 'name', '') or ''),
                                ai_model=(ai_meta.get('model') if isinstance(ai_meta, dict) else '') or '',
                                ai_provider=(ai_meta.get('provider') if isinstance(ai_meta, dict) else '') or '',
                                success=True, external_id=str((body.get('id') if isinstance(body, dict) else '') or ''), error_code='', error_message='',
                            )
                        except Exception:
                            pass
                        try:
                            record_success_run(owner_id=task.owner_id, provider='facebook', task_type='reply_comment', started_date=timezone.now().date())
                        except Exception:
                            pass
                else:
                    results.append({'account_id': acc.id, 'status': 'skipped', 'reason': 'unsupported_provider'})
            except Exception as e:
                code = _extract_status_code(e)
                try:
                    _mark_account_by_code(acc, code)
                except Exception:
                    pass
                results.append({'account_id': acc.id, 'status': 'error', 'error': str(e), 'code': code, 'account_status': acc.status})
                err_count += 1
                try:
                    SimpleTaskRun.objects.create(
                        task=task, owner_id=task.owner_id, provider=task.provider, type=task.type,
                        account=acc, text=text, used_prompt=(getattr(task.prompt, 'name', '') or ''),
                        ai_model=(ai_meta.get('model') if isinstance(ai_meta, dict) else '') or '',
                        ai_provider=(ai_meta.get('provider') if isinstance(ai_meta, dict) else '') or '',
                        success=False, external_id='', error_code=str(code or ''), error_message=str(e),
                    )
                except Exception:
                    pass
        # 运行完成：写入 last_text，将仍为 active 的账号改回 inactive
        if selected_ids:
            try:
                PoolAccount.objects.filter(id__in=selected_ids, status='active').update(status='inactive')
            except Exception:
                pass
        try:
            task.last_text = text
            task.save(update_fields=['last_text'])
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
            # return Response({'status': 'failed', 'ai_meta': ai_meta, 'summary': {'ok': ok_count, 'error': err_count}, 'results': results})
        return Response({'status': 'ok', 'ai_meta': ai_meta, 'summary': {'ok': ok_count, 'error': err_count}, 'results': results})

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
