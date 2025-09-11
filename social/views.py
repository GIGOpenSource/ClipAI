from django.conf import settings
from django.core.cache import cache
import os
import base64
import hashlib
import secrets
import urllib.parse
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
from accounts.models import AuditLog
from requests_oauthlib import OAuth1
import tweepy
from django.utils import timezone
from datetime import datetime


class WebhookReceiver(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='社交平台 Webhook（占位，默认关闭）', tags=['Webhook'])
    def post(self, request, provider: str):
        if not getattr(settings, 'WEBHOOKS_ENABLED', False):
            return Response({'detail': 'webhooks disabled'}, status=404)
        # 占位：仅记录审计日志，不执行业务
        AuditLog.objects.create(
            actor=None,
            action=f'webhook.{provider}.received',
            target_type='webhook',
            target_id='',
            success=True,
            metadata={'headers': dict(request.headers), 'body': request.data},
        )
        return Response({'status': 'ok'})

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse
from accounts.permissions import IsStaffUser, IsOwnerOrAdmin
from .models import SocialConfig, SocialAccount
from .serializers import SocialConfigSerializer, SocialAccountSerializer


@extend_schema_view(
    list=extend_schema(summary='社交平台配置列表', tags=['社交配置']),
    retrieve=extend_schema(summary='社交平台配置详情', tags=['社交配置']),
    create=extend_schema(summary='创建社交平台配置', tags=['社交配置']),
    update=extend_schema(summary='更新社交平台配置', tags=['社交配置']),
    partial_update=extend_schema(summary='部分更新社交平台配置', tags=['社交配置']),
    destroy=extend_schema(summary='删除社交平台配置', tags=['社交配置'])
)
class SocialConfigViewSet(viewsets.ModelViewSet):
    queryset = SocialConfig.objects.all().order_by('-created_at')
    serializer_class = SocialConfigSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        # 多租户过滤：管理员默认全量；普通用户仅自己的
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            user_id = self.request.query_params.get('user_id')
            if user_id:
                qs = qs.filter(owner_id=user_id)
        else:
            user_id = self.request.user.id if self.request.user and self.request.user.is_authenticated else None
            qs = qs.filter(owner_id=user_id) if user_id else qs.none()
        provider = self.request.query_params.get('provider')
        if provider:
            qs = qs.filter(provider=provider)
        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(name__icontains=q)
        enabled = self.request.query_params.get('enabled')
        if enabled in {'true', 'false'}:
            qs = qs.filter(enabled=(enabled == 'true'))
        ordering = self.request.query_params.get('ordering')
        if ordering in {'name', '-name', 'priority', '-priority', 'created_at', '-created_at'}:
            qs = qs.order_by(ordering)
        return qs

    def perform_create(self, serializer):
        # 普通用户仅能创建归属于自己的配置；管理员可通过 body.owner 指定
        if self.request.user and self.request.user.is_authenticated and not self.request.user.is_staff:
            serializer.save(owner=self.request.user)
        else:
            serializer.save()

    @extend_schema(summary='导入开发者平台信息（导入到当前登录用户）', tags=['社交配置'])
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def import_my_config(self, request):
        payload = request.data.copy()
        provider = (payload.get('provider') or '').lower()

        # Normalize provider-specific aliases for config fields
        if provider == 'twitter':
            if payload.get('api_key') and not payload.get('client_id'):
                payload['client_id'] = payload.get('api_key')
            if payload.get('api_secret') and not payload.get('client_secret'):
                payload['client_secret'] = payload.get('api_secret')
        if provider in {'facebook', 'instagram'}:
            if payload.get('client_id') and not payload.get('app_id'):
                payload['app_id'] = payload.get('client_id')
            if payload.get('client_secret') and not payload.get('app_secret'):
                payload['app_secret'] = payload.get('client_secret')

        # Normalize redirect_uris and scopes formats
        if payload.get('redirect_uri') and not payload.get('redirect_uris'):
            payload['redirect_uris'] = [payload.get('redirect_uri')]
        if isinstance(payload.get('redirect_uris'), str):
            payload['redirect_uris'] = [u.strip() for u in payload['redirect_uris'].split(',') if u.strip()]
        scopes_val = payload.get('scopes')
        if isinstance(scopes_val, str):
            payload['scopes'] = [p.strip() for p in scopes_val.replace(',', ' ').split() if p.strip()]
        # Apply provider defaults when scopes missing/invalid (prefer read+write minimal set)
        if not isinstance(payload.get('scopes'), list) or len(payload.get('scopes') or []) == 0:
            if provider == 'twitter':
                payload['scopes'] = ['tweet.read', 'tweet.write', 'users.read']
            elif provider == 'facebook':
                payload['scopes'] = ['public_profile', 'pages_read_engagement', 'pages_manage_posts']
            elif provider == 'instagram':
                payload['scopes'] = ['user_profile', 'user_media']
            elif provider == 'threads':
                payload['scopes'] = ['threads_basic', 'threads_content_publish']
            else:
                payload['scopes'] = []
        # 强制归属到当前用户，忽略传入的 owner/created_by
        payload.pop('owner', None)
        payload.pop('created_by', None)
        # 拆出账号令牌信息（可选）
        account_data = payload.pop('account', None)
        # Normalize provider-specific account fields from top-level into account
        acc_alias = {}
        if provider == 'twitter':
            if payload.get('oauth1_user_token'):
                acc_alias['access_token'] = payload.get('oauth1_user_token')
            if payload.get('oauth1_user_token_secret'):
                acc_alias['refresh_token'] = payload.get('oauth1_user_token_secret')
            if payload.get('account_external_user_id'):
                acc_alias['external_user_id'] = payload.get('account_external_user_id')
            if payload.get('account_external_username'):
                acc_alias['external_username'] = payload.get('account_external_username')
        elif provider == 'facebook':
            token = payload.get('page_access_token') or payload.get('user_access_token')
            if token:
                acc_alias['access_token'] = token
            if payload.get('account_external_user_id'):
                acc_alias['external_user_id'] = payload.get('account_external_user_id')
            if payload.get('account_external_username'):
                acc_alias['external_username'] = payload.get('account_external_username')
        elif provider == 'instagram':
            if payload.get('ig_user_access_token'):
                acc_alias['access_token'] = payload.get('ig_user_access_token')
            if payload.get('account_external_user_id'):
                acc_alias['external_user_id'] = payload.get('account_external_user_id')
            if payload.get('account_external_username'):
                acc_alias['external_username'] = payload.get('account_external_username')
        if payload.get('account_status'):
            acc_alias['status'] = payload.get('account_status')
        if payload.get('account_scopes') and isinstance(payload.get('account_scopes'), str):
            acc_alias['scopes'] = [p.strip() for p in payload.get('account_scopes').replace(',', ' ').split() if p.strip()]
        if payload.get('account_expires_at'):
            acc_alias['expires_at'] = payload.get('account_expires_at')
        if acc_alias:
            if not isinstance(account_data, dict):
                account_data = {}
            account_data.update({k: v for k, v in acc_alias.items() if v is not None})
        # If account scopes still missing, inherit from config scopes
        if isinstance(account_data, dict) and 'scopes' not in account_data:
            account_data['scopes'] = payload.get('scopes') or []
        # 若传入 config_id 则更新，否则创建
        config_id = payload.pop('config_id', None)
        instance = None
        if config_id:
            instance = SocialConfig.objects.filter(id=config_id, owner=request.user).first()
        serializer = self.get_serializer(instance=instance, data=payload, partial=bool(instance))
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(owner=request.user, created_by=request.user)
        # 若标记为默认，则清理同 owner+provider 其它默认
        try:
            if getattr(instance, 'is_default', False):
                SocialConfig.objects.filter(owner=instance.owner, provider=instance.provider, is_default=True).exclude(pk=instance.pk).update(is_default=False)
        except Exception:
            pass
        resp = self.get_serializer(instance).data
        # 写入账号令牌（可选）
        if isinstance(account_data, dict):
            ext_id = account_data.get('external_user_id') or ''
            ext_name = account_data.get('external_username') or ''
            acc, _ = SocialAccount.objects.get_or_create(
                owner=request.user,
                provider=instance.provider,
                external_user_id=ext_id or str(request.user.id),
                defaults={'status': account_data.get('status', 'active')}
            )
            if 'access_token' in account_data:
                acc.set_access_token(account_data.get('access_token'))
            if 'refresh_token' in account_data:
                acc.set_refresh_token(account_data.get('refresh_token'))
            exp = account_data.get('expires_at')
            if exp:
                try:
                    if isinstance(exp, int):
                        acc.expires_at = timezone.now() + timezone.timedelta(seconds=exp)
                    elif isinstance(exp, str):
                        # ISO 格式
                        acc.expires_at = datetime.fromisoformat(exp)
                except Exception:
                    acc.expires_at = None
            if ext_name:
                acc.external_username = ext_name
            if isinstance(account_data.get('scopes'), list):
                acc.scopes = account_data.get('scopes')
            if account_data.get('status'):
                acc.status = account_data.get('status')
            acc.config = instance
            acc.save()
            resp['account_id'] = acc.id
        return Response(resp, status=201)

    @extend_schema(summary='设为平台默认', tags=['社交配置'])
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        cfg = self.get_object()
        SocialConfig.objects.filter(provider=cfg.provider, is_default=True).update(is_default=False)
        cfg.is_default = True
        cfg.save(update_fields=['is_default'])
        return Response({'status': 'ok'})

    @extend_schema(summary='获取平台默认配置', tags=['社交配置'])
    @action(detail=False, methods=['get'])
    def default(self, request):
        provider = request.query_params.get('provider')
        if not provider:
            return Response({'detail': '缺少 provider'}, status=400)
        user_id = request.query_params.get('user_id') or (request.user.id if request.user.is_authenticated else None)
        qs = SocialConfig.objects.filter(provider=provider, enabled=True)
        if user_id:
            qs = qs.filter(owner_id=user_id)
        cfg = qs.filter(is_default=True).first()
        if not cfg:
            cfg = qs.order_by('-priority', 'name').first()
        if not cfg:
            return Response({'detail': '未找到配置'}, status=404)
        return Response(self.get_serializer(cfg).data)

    @extend_schema(summary='测试连通性（字段校验）', tags=['社交配置'], responses={200: OpenApiResponse(description='校验成功')})
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        cfg = self.get_object()
        # 仅做必填校验，不调用外部 API
        errors = []
        if cfg.provider == 'twitter' and (not cfg.client_id or not cfg.client_secret):
            errors.append('Twitter 需要 client_id 与 client_secret')
        if cfg.provider == 'facebook' and (not cfg.app_id or not cfg.app_secret):
            errors.append('Facebook 需要 app_id 与 app_secret')
        if cfg.provider == 'instagram' and (not cfg.app_id or not cfg.app_secret):
            errors.append('Instagram 需要 app_id 与 app_secret')
        if errors:
            return Response({'detail': '；'.join(errors)}, status=400)
        return Response({'status': 'ok'})

    @extend_schema(summary='平台元数据（字段提示）', tags=['社交配置'])
    @action(detail=False, methods=['get'])
    def providers(self, request):
        data = {
            'twitter': {
                'required': ['client_id', 'client_secret'],
                'optional': ['bearer_token', 'api_version', 'redirect_uris', 'scopes', 'webhook_verify_token', 'signing_secret']
            },
            'facebook': {
                'required': ['app_id', 'app_secret'],
                'optional': ['api_version', 'redirect_uris', 'scopes', 'page_id', 'page_access_token', 'webhook_verify_token']
            },
            'instagram': {
                'required': ['app_id', 'app_secret'],
                'optional': ['api_version', 'redirect_uris', 'scopes', 'ig_business_account_id']
            },
            'threads': {
                'required': ['app_id', 'app_secret'],
                'optional': ['api_version', 'redirect_uris', 'scopes', 'user_id', 'page_access_token']
            },
        }
        return Response(data)

class SocialAccountHealthView(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    @extend_schema(summary='触发社交账号健康检查（异步）', tags=['社交账户'])
    def post(self, request):
        from .tasks import check_social_accounts_health
        check_social_accounts_health.delay()
        return Response({'status': 'queued'})


@extend_schema_view(
    list=extend_schema(summary='社交账号列表', tags=['社交账户']),
    retrieve=extend_schema(summary='社交账号详情', tags=['社交账户']),
    create=extend_schema(summary='创建社交账号', tags=['社交账户']),
    update=extend_schema(summary='更新社交账号', tags=['社交账户']),
    partial_update=extend_schema(summary='部分更新社交账号', tags=['社交账户']),
    destroy=extend_schema(summary='删除社交账号', tags=['社交账户'])
)
class SocialAccountViewSet(viewsets.ModelViewSet):
    queryset = SocialAccount.objects.all().order_by('-updated_at')
    serializer_class = SocialAccountSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user and user.is_authenticated and user.is_staff:
            user_id = self.request.query_params.get('user_id')
            if user_id:
                qs = qs.filter(owner_id=user_id)
        else:
            uid = user.id if user and user.is_authenticated else None
            qs = qs.filter(owner_id=uid) if uid else qs.none()
        provider = self.request.query_params.get('provider')
        if provider:
            qs = qs.filter(provider=provider)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        # 普通用户只能创建归属于自己的；管理员可指定 owner
        if user and user.is_authenticated and not user.is_staff:
            serializer.save(owner=user)
        else:
            serializer.save()

# ---- Twitter OAuth2 (PKCE) minimal flow ----

class TwitterOAuthStart(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    @extend_schema(summary='Twitter OAuth2 开始（返回授权链接）', tags=['社交账户'])
    def get(self, request):
        from .models import SocialConfig
        user_id = request.query_params.get('user_id') or (request.user.id if request.user.is_authenticated else None)
        cfg = SocialConfig.objects.filter(provider='twitter', enabled=True).order_by('-is_default', '-priority').first()
        if not cfg:
            return Response({'detail': '未找到 Twitter 配置'}, status=404)
        if not cfg.client_id:
            return Response({'detail': '缺少 client_id'}, status=400)
        redirect_uris = cfg.redirect_uris or []
        if not redirect_uris:
            return Response({'detail': 'Twitter 配置缺少 redirect_uris'}, status=400)
        # 支持 per-user 回调地址：当传入 use_user_callback=true 时，构造 /api/social/oauth/twitter/callback/<user_id>/
        use_user_cb = request.query_params.get('use_user_callback') in {'1','true','yes'}
        if use_user_cb and user_id:
            host = request.build_absolute_uri('/')[:-1]
            redirect_uri = host + f"/api/social/oauth/twitter/callback/{user_id}/"
        else:
            redirect_uri = redirect_uris[0]
        scopes = cfg.scopes or ['tweet.read', 'users.read']
        # PKCE
        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('=')
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip('=')
        state = secrets.token_urlsafe(16)
        cache.set(f'oauth2:tw:{state}', {'code_verifier': code_verifier, 'user_id': user_id, 'cfg_id': cfg.id, 'redirect_uri': redirect_uri}, timeout=900)
        params = {
            'response_type': 'code',
            'client_id': cfg.client_id,
            'redirect_uri': redirect_uri,
            'scope': ' '.join(scopes),
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        }
        auth_url = 'https://twitter.com/i/oauth2/authorize?' + urllib.parse.urlencode(params)
        return Response({'auth_url': auth_url, 'state': state, 'redirect_uri': redirect_uri, 'scopes': scopes})


class TwitterOAuthCallback(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='Twitter OAuth2 回调（换取用户 token 并绑定 SocialAccount）', tags=['社交账户'])
    def get(self, request, user_id: int | None = None):
        from .models import SocialConfig, SocialAccount
        code = request.query_params.get('code')
        state = request.query_params.get('state')
        if not code or not state:
            return Response({'detail': '缺少 code/state'}, status=400)
        ctx = cache.get(f'oauth2:tw:{state}')
        if not ctx:
            return Response({'detail': 'state 无效或已过期'}, status=400)
        cache.delete(f'oauth2:tw:{state}')
        code_verifier = ctx['code_verifier']
        # 优先使用 URL 参数中的 user_id（per-user 回调），其次取 state 里的 user_id
        user_id = user_id or ctx.get('user_id')
        cfg = SocialConfig.objects.filter(id=ctx.get('cfg_id')).first()
        if not cfg:
            return Response({'detail': '配置不存在'}, status=400)
        redirect_uri = ctx.get('redirect_uri') or (cfg.redirect_uris or [None])[0]
        if not redirect_uri:
            return Response({'detail': '配置缺少 redirect_uri'}, status=400)
# Create your views here.


# ---- Facebook OAuth2 (Authorization Code) ----

class FacebookOAuthStart(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    @extend_schema(summary='Facebook OAuth2 开始（返回授权链接）', tags=['社交账户'])
    def get(self, request):
        from .models import SocialConfig
        user_id = request.query_params.get('user_id') or (request.user.id if request.user.is_authenticated else None)
        cfg = SocialConfig.objects.filter(provider='facebook', enabled=True).order_by('-is_default', '-priority').first()
        if not cfg:
            return Response({'detail': '未找到 Facebook 配置'}, status=404)
        app_id = cfg.app_id or cfg.client_id
        app_secret = cfg.app_secret or cfg.client_secret
        if not app_id or not app_secret:
            return Response({'detail': '缺少 app_id/client_id 或 app_secret/client_secret'}, status=400)
        redirect_uris = cfg.redirect_uris or []
        if not redirect_uris:
            return Response({'detail': 'Facebook 配置缺少 redirect_uris'}, status=400)
        use_user_cb = request.query_params.get('use_user_callback') in {'1','true','yes'}
        if use_user_cb and user_id:
            host = request.build_absolute_uri('/')[:-1]
            redirect_uri = host + f"/api/social/oauth/facebook/callback/{user_id}/"
        else:
            redirect_uri = redirect_uris[0]
        scopes = cfg.scopes or ['public_profile']
        api_ver = cfg.api_version or 'v19.0'

        state = secrets.token_urlsafe(16)
        cache.set(f'oauth2:fb:{state}', {'user_id': user_id, 'cfg_id': cfg.id, 'redirect_uri': redirect_uri}, timeout=900)
        params = {
            'client_id': app_id,
            'redirect_uri': redirect_uri,
            'state': state,
            'response_type': 'code',
            'scope': ','.join(scopes),
        }
        auth_url = f'https://www.facebook.com/{api_ver}/dialog/oauth?' + urllib.parse.urlencode(params)
        return Response({'auth_url': auth_url, 'state': state, 'redirect_uri': redirect_uri, 'scopes': scopes})


class FacebookOAuthCallback(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='Facebook OAuth2 回调（换取用户 token 并绑定 SocialAccount）', tags=['社交账户'])
    def get(self, request, user_id: int | None = None):
        from .models import SocialConfig, SocialAccount
        code = request.query_params.get('code')
        state = request.query_params.get('state')
        if not code or not state:
            return Response({'detail': '缺少 code/state'}, status=400)
        ctx = cache.get(f'oauth2:fb:{state}')
        if not ctx:
            return Response({'detail': 'state 无效或已过期'}, status=400)
        cache.delete(f'oauth2:fb:{state}')
        cfg = SocialConfig.objects.filter(id=ctx.get('cfg_id')).first()
        if not cfg:
            return Response({'detail': '配置不存在'}, status=400)
        app_id = cfg.app_id or cfg.client_id
        app_secret = cfg.app_secret or cfg.client_secret
        # per-user redirect_uri from state has priority
        redirect_uri = ctx.get('redirect_uri') or (cfg.redirect_uris or [None])[0]
        api_ver = cfg.api_version or 'v19.0'
        if not (app_id and app_secret and redirect_uri):
            return Response({'detail': '配置缺少 app_id/app_secret/redirect_uri'}, status=400)
        token_url = f'https://graph.facebook.com/{api_ver}/oauth/access_token'
        try:
            tr = requests.get(token_url, params={
                'client_id': app_id,
                'redirect_uri': redirect_uri,
                'client_secret': app_secret,
                'code': code,
            }, timeout=20)
            tr.raise_for_status()
            tk = tr.json()
        except requests.RequestException as e:
            return Response({'detail': 'token 交换失败', 'error': str(e), 'body': getattr(e.response, 'text', '')}, status=400)
        access_token = tk.get('access_token')
        # 获取用户信息
        me = None
        try:
            mr = requests.get(f'https://graph.facebook.com/{api_ver}/me', params={'access_token': access_token, 'fields': 'id,name'}, timeout=20)
            mr.raise_for_status()
            me = mr.json()
        except requests.RequestException as e:
            me = {'error': str(e), 'body': getattr(e.response, 'text', '')}
        owner_id = (user_id or ctx.get('user_id')) or (request.user.id if request.user and request.user.is_authenticated else None)
        if not owner_id:
            return Response({'detail': '缺少 owner_id'}, status=400)
        ext_id = (me or {}).get('id')
        ext_name = (me or {}).get('name') or ''
        acc, _ = SocialAccount.objects.get_or_create(owner_id=owner_id, provider='facebook', external_user_id=ext_id or str(owner_id), defaults={'status': 'active'})
        if access_token:
            acc.set_access_token(access_token)
        if ext_name:
            acc.external_username = ext_name
        acc.scopes = cfg.scopes or []
        acc.status = 'active'
        acc.expires_at = None
        acc.save()
        return Response({'status': 'ok', 'account_id': acc.id, 'me': me, 'token': {k: tk.get(k) for k in ['token_type','expires_in'] if k in tk}})


# ---- Instagram OAuth (Basic Display, simplified) ----

class InstagramOAuthStart(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    @extend_schema(summary='Instagram OAuth 开始（返回授权链接）', tags=['社交账户'])
    def get(self, request):
        from .models import SocialConfig
        user_id = request.query_params.get('user_id') or (request.user.id if request.user.is_authenticated else None)
        cfg = SocialConfig.objects.filter(provider='instagram', enabled=True).order_by('-is_default', '-priority').first()
        if not cfg:
            return Response({'detail': '未找到 Instagram 配置'}, status=404)
        app_id = cfg.app_id or cfg.client_id
        app_secret = cfg.app_secret or cfg.client_secret
        if not app_id or not app_secret:
            return Response({'detail': '缺少 app_id/client_id 或 app_secret/client_secret'}, status=400)
        redirect_uris = cfg.redirect_uris or []
        if not redirect_uris:
            return Response({'detail': 'Instagram 配置缺少 redirect_uris'}, status=400)
        use_user_cb = request.query_params.get('use_user_callback') in {'1','true','yes'}
        if use_user_cb and user_id:
            host = request.build_absolute_uri('/')[:-1]
            redirect_uri = host + f"/api/social/oauth/instagram/callback/{user_id}/"
        else:
            redirect_uri = redirect_uris[0]
        scopes = cfg.scopes or ['user_profile']
        state = secrets.token_urlsafe(16)
        cache.set(f'oauth2:ig:{state}', {'user_id': user_id, 'cfg_id': cfg.id, 'redirect_uri': redirect_uri}, timeout=900)
        params = {
            'client_id': app_id,
            'redirect_uri': redirect_uri,
            'scope': ' '.join(scopes),
            'response_type': 'code',
            'state': state,
        }
        auth_url = 'https://api.instagram.com/oauth/authorize?' + urllib.parse.urlencode(params)
        return Response({'auth_url': auth_url, 'state': state, 'redirect_uri': redirect_uri, 'scopes': scopes})


class InstagramOAuthCallback(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='Instagram OAuth 回调（换取用户 token 并绑定 SocialAccount）', tags=['社交账户'])
    def get(self, request, user_id: int | None = None):
        from .models import SocialConfig, SocialAccount
        code = request.query_params.get('code')
        state = request.query_params.get('state')
        if not code or not state:
            return Response({'detail': '缺少 code/state'}, status=400)
        ctx = cache.get(f'oauth2:ig:{state}')
        if not ctx:
            return Response({'detail': 'state 无效或已过期'}, status=400)
        cache.delete(f'oauth2:ig:{state}')
        cfg = SocialConfig.objects.filter(id=ctx.get('cfg_id')).first()
        if not cfg:
            return Response({'detail': '配置不存在'}, status=400)
        app_id = cfg.app_id or cfg.client_id
        app_secret = cfg.app_secret or cfg.client_secret
        redirect_uri = ctx.get('redirect_uri') or (cfg.redirect_uris or [None])[0]
        if not (app_id and app_secret and redirect_uri):
            return Response({'detail': '配置缺少 app_id/app_secret/redirect_uri'}, status=400)
        try:
            tr = requests.post('https://api.instagram.com/oauth/access_token', data={
                'client_id': app_id,
                'client_secret': app_secret,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri,
                'code': code,
            }, timeout=20)
            tr.raise_for_status()
            tk = tr.json()
        except requests.RequestException as e:
            return Response({'detail': 'token 交换失败', 'error': str(e), 'body': getattr(e.response, 'text', '')}, status=400)
        access_token = tk.get('access_token')
        me = None
        try:
            mr = requests.get('https://graph.instagram.com/me', params={'fields': 'id,username', 'access_token': access_token}, timeout=20)
            mr.raise_for_status()
            me = mr.json()
        except requests.RequestException as e:
            me = {'error': str(e), 'body': getattr(e.response, 'text', '')}
        owner_id = (user_id or ctx.get('user_id')) or (request.user.id if request.user and request.user.is_authenticated else None)
        if not owner_id:
            return Response({'detail': '缺少 owner_id'}, status=400)
        ext_id = (me or {}).get('id')
        ext_name = (me or {}).get('username') or ''
        acc, _ = SocialAccount.objects.get_or_create(owner_id=owner_id, provider='instagram', external_user_id=ext_id or str(owner_id), defaults={'status': 'active'})
        if access_token:
            acc.set_access_token(access_token)
        if ext_name:
            acc.external_username = ext_name
        acc.scopes = cfg.scopes or []
        acc.status = 'active'
        acc.expires_at = None
        acc.save()
        return Response({'status': 'ok', 'account_id': acc.id, 'me': me, 'token': {k: tk.get(k) for k in ['token_type','expires_in'] if k in tk}})
