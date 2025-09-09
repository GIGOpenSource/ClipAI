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
from .serializers import SocialConfigSerializer


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
        # 强制归属到当前用户，忽略传入的 owner/created_by
        payload.pop('owner', None)
        payload.pop('created_by', None)
        # 拆出账号令牌信息（可选）
        account_data = payload.pop('account', None)
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
        }
        return Response(data)

class SocialAccountHealthView(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    @extend_schema(summary='触发社交账号健康检查（异步）', tags=['社交账户'])
    def post(self, request):
        from .tasks import check_social_accounts_health
        check_social_accounts_health.delay()
        return Response({'status': 'queued'})

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
        redirect_uri = redirect_uris[0]
        scopes = cfg.scopes or ['tweet.read', 'users.read']
        # PKCE
        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('=')
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip('=')
        state = secrets.token_urlsafe(16)
        cache.set(f'oauth2:tw:{state}', {'code_verifier': code_verifier, 'user_id': user_id, 'cfg_id': cfg.id}, timeout=900)
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
    def get(self, request):
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
        user_id = ctx.get('user_id')
        cfg = SocialConfig.objects.filter(id=ctx.get('cfg_id')).first()
        if not cfg:
            return Response({'detail': '配置不存在'}, status=400)
        redirect_uri = (cfg.redirect_uris or [None])[0]
        if not redirect_uri:
            return Response({'detail': '配置缺少 redirect_uri'}, status=400)
        token_url = 'https://api.twitter.com/2/oauth2/token'
        data = {
            'grant_type': 'authorization_code',
            'client_id': cfg.client_id,
            'code': code,
            'code_verifier': code_verifier,
            'redirect_uri': redirect_uri,
        }
        try:
            tr = requests.post(token_url, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=20)
            tr.raise_for_status()
            tk = tr.json()
        except requests.RequestException as e:
            return Response({'detail': 'token 交换失败', 'error': str(e), 'body': getattr(e.response, 'text', '')}, status=400)
        access_token = tk.get('access_token')
        refresh_token = tk.get('refresh_token')
        expires_in = tk.get('expires_in')
        # 拉取当前用户信息
        me = None
        try:
            hr = requests.get('https://api.twitter.com/2/users/me', headers={'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'}, timeout=20)
            hr.raise_for_status()
            me = hr.json()
        except requests.RequestException as e:
            # 即便失败也允许先落库，方便后续人工排查
            me = {'error': str(e), 'body': getattr(e.response, 'text', '')}
        # 绑定/更新 SocialAccount
        from django.utils import timezone as dj_tz
        owner_id = user_id
        if not owner_id and request.user and request.user.is_authenticated:
            owner_id = request.user.id
        if not owner_id:
            return Response({'detail': '缺少 owner_id，请在 start 时传 user_id 或在已登录状态下发起'}, status=400)
        ext_id = None
        ext_name = ''
        try:
            ext = (me or {}).get('data') or {}
            ext_id = ext.get('id')
            ext_name = ext.get('username') or ''
        except Exception:
            pass
        acc, _ = SocialAccount.objects.get_or_create(owner_id=owner_id, provider='twitter', external_user_id=ext_id or str(owner_id), defaults={'status': 'active'})
        if access_token:
            acc.set_access_token(access_token)
        if refresh_token:
            acc.set_refresh_token(refresh_token)
        if ext_name:
            acc.external_username = ext_name
        acc.status = 'active'
        acc.expires_at = None
        acc.save()
        return Response({'status': 'ok', 'account_id': acc.id, 'me': me, 'token': {k: tk.get(k) for k in ['token_type','scope','expires_in']}})


class TwitterMeOAuth1(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    @extend_schema(summary='Twitter OAuth1 读取 users/me（只读计划诊断）', tags=['社交账户'])
    def get(self, request):
        from .models import SocialConfig, SocialAccount
        from tasks.clients import TwitterClient
        cfg = SocialConfig.objects.filter(provider='twitter').order_by('-is_default', '-priority').first()
        if not cfg or not cfg.client_id or not cfg.client_secret:
            return Response({'detail': '需要在 SocialConfig 填写 client_id(API key)/client_secret(API secret key)'}, status=400)
        acc = SocialAccount.objects.filter(provider='twitter', status='active').order_by('-updated_at').first()
        if not acc or not acc.access_token:
            return Response({'detail': '需要在 SocialAccount 填写 access_token（OAuth1 用户 token）与（可选）refresh_token=access_token_secret'}, status=400)
        user_token = acc.access_token
        token_secret = acc.refresh_token or ''  # 暂存到 refresh_token 字段
        try:
            client = TwitterClient(consumer_key=cfg.client_id, consumer_secret=cfg.client_secret, access_token=user_token, access_token_secret=token_secret)
            body, rl = client.get_me_with_headers()
            return Response({'status': 200, 'body': body, 'rate_limit': rl})
        except Exception as e:
            return Response({'detail': '请求失败', 'error': str(e)}, status=400)
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
        redirect_uri = redirect_uris[0]
        scopes = cfg.scopes or ['public_profile']
        api_ver = cfg.api_version or 'v19.0'

        state = secrets.token_urlsafe(16)
        cache.set(f'oauth2:fb:{state}', {'user_id': user_id, 'cfg_id': cfg.id}, timeout=900)
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
    def get(self, request):
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
        redirect_uri = (cfg.redirect_uris or [None])[0]
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
        owner_id = ctx.get('user_id') or (request.user.id if request.user and request.user.is_authenticated else None)
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
        redirect_uri = redirect_uris[0]
        scopes = cfg.scopes or ['user_profile']
        state = secrets.token_urlsafe(16)
        cache.set(f'oauth2:ig:{state}', {'user_id': user_id, 'cfg_id': cfg.id}, timeout=900)
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
    def get(self, request):
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
        redirect_uri = (cfg.redirect_uris or [None])[0]
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
        owner_id = ctx.get('user_id') or (request.user.id if request.user and request.user.is_authenticated else None)
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
