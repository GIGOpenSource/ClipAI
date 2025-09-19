from django.core.cache import cache
import os
import base64
import hashlib
import secrets
import urllib.parse
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse
import tweepy
from django.utils import timezone
from django.http import HttpRequest

from rest_framework import viewsets
from rest_framework.decorators import action
from accounts.permissions import IsStaffUser
from .models import PoolAccount
from .serializers import PoolAccountSerializer


@extend_schema_view(
    list=extend_schema(summary='账号池列表', tags=['账号池']),
    retrieve=extend_schema(summary='账号池详情', tags=['账号池']),
    create=extend_schema(summary='创建账号池账号', tags=['账号池']),
    update=extend_schema(summary='更新账号池账号', tags=['账号池']),
    partial_update=extend_schema(summary='部分更新账号池账号', tags=['账号池']),
    destroy=extend_schema(summary='删除账号池账号', tags=['账号池'])
)
class PoolAccountViewSet(viewsets.ModelViewSet):
    queryset = PoolAccount.objects.all().order_by('-updated_at')
    serializer_class = PoolAccountSerializer
    permission_classes = [IsAuthenticated, IsStaffUser] # 用户权限

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        provider = self.request.query_params.get('provider')
        status_v = self.request.query_params.get('status')
        name_q = self.request.query_params.get('q')
        getrname_q = self.request.query_params.get('name')
        remark_q = self.request.query_params.get('remark')  # 添加备注查询参数
        remark_exact = self.request.query_params.get('remark_exact')  # 精确匹配查询参数
        # 权限隔离：普通用户只能看到自己创建的账户
        if not user.is_staff:
            if hasattr(self.queryset.model, 'owner'):
                qs = qs.filter(owner=user)
            else:
                # 如果没有 owner 字段，普通用户只能看到状态为 active 的公共账户
                qs = qs.filter(status='active')
        if provider:
            qs = qs.filter(provider=provider)
        if status_v:
            qs = qs.filter(status=status_v)
        if name_q:
            qs = qs.filter(name__icontains=name_q)
            # 添加备注字段的筛选
        if getrname_q:
            qs = qs.filter(name=getrname_q)
        if remark_q:
            # 模糊匹配
            qs = qs.filter(remark__icontains=remark_q)
        if remark_exact:
            # 精确匹配
            qs = qs.filter(remark=remark_exact)
        return qs

    def perform_create(self, serializer):
        # 创建时自动设置所有者
        user = self.request.user
        if hasattr(serializer.Meta.model, 'owner'):
            serializer.save(owner=user)
        else:
            serializer.save()

# ---- OAuth for PoolAccount (Twitter OAuth1.0a and Facebook OAuth2 minimal) ----

class PoolAccountTwitterOAuthStart(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    @extend_schema(summary='账号池 Twitter OAuth1.0a 开始（返回请求token）', tags=['账号池'])
    def get(self, request):
        api_key = request.query_params.get('api_key')
        api_secret = request.query_params.get('api_secret')
        if not api_key or not api_secret:
            return Response({'detail': '缺少 api_key/api_secret'}, status=400)
        callback_url = request.build_absolute_uri('/api/social/oauth/pool/twitter/callback/')
        auth = tweepy.OAuth1UserHandler(api_key, api_secret, callback=callback_url)
        try:
            redirect_url = auth.get_authorization_url()
            request_token = auth.request_token or {}
            oauth_token = request_token.get('oauth_token')
            oauth_token_secret = request_token.get('oauth_token_secret')
            if oauth_token and oauth_token_secret:
                cache.set(f'pool:tw:{oauth_token}', {
                    'oauth_token_secret': oauth_token_secret,
                    'api_key': api_key,
                    'api_secret': api_secret,
                }, timeout=900)
            return Response({'auth_url': redirect_url})
        except Exception as e:
            return Response({'detail': '获取授权地址失败', 'error': str(e)}, status=400)


class PoolAccountTwitterOAuthCallback(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='账号池 Twitter OAuth1.0a 回调（保存用户token到 PoolAccount）', tags=['账号池'])
    def get(self, request):
        oauth_token = request.query_params.get('oauth_token')
        verifier = request.query_params.get('oauth_verifier')
        ctx = cache.get(f'pool:tw:{oauth_token}') if oauth_token else None
        if not ctx:
            return Response({'detail': '请求 token 无效或过期'}, status=400)
        api_key = ctx.get('api_key')
        api_secret = ctx.get('api_secret')
        oauth_token_secret = ctx.get('oauth_token_secret')
        auth = tweepy.OAuth1UserHandler(api_key, api_secret)
        auth.request_token = {'oauth_token': oauth_token, 'oauth_token_secret': oauth_token_secret}
        try:
            access_token, access_token_secret = auth.get_access_token(verifier)
        except Exception as e:
            return Response({'detail': '交换 token 失败', 'error': str(e)}, status=400)
        acc = PoolAccount.objects.create(
            provider='twitter',
            name=f"tw-{timezone.now().strftime('%Y%m%d-%H%M%S')}",
            api_key=api_key,
            api_secret=api_secret,
            is_ban=False,
            status='active',
        )
        acc.set_access_token(access_token)
        acc.set_access_token_secret(access_token_secret)
        acc.save()
        cache.delete(f'pool:tw:{oauth_token}')
        return Response({'status': 'ok', 'pool_account_id': acc.id})


class PoolAccountFacebookOAuthStart(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    @extend_schema(summary='账号池 Facebook OAuth2 开始（返回授权链接）', tags=['账号池'])
    def get(self, request):
        app_id = request.query_params.get('app_id') or request.query_params.get('client_id')
        app_secret = request.query_params.get('app_secret') or request.query_params.get('client_secret')
        api_version = request.query_params.get('api_version') or 'v19.0'
        scopes_raw = request.query_params.get('scopes') or 'public_profile,pages_manage_posts'
        scopes = [s.strip() for s in scopes_raw.split(',') if s.strip()]
        if not app_id or not app_secret:
            return Response({'detail': '缺少 app_id/client_id 或 app_secret/client_secret'}, status=400)
        redirect_uri = request.build_absolute_uri('/api/social/oauth/pool/facebook/callback/')
        state = secrets.token_urlsafe(16)
        cache.set(f'pool:fb:{state}', {'app_id': app_id, 'app_secret': app_secret, 'redirect_uri': redirect_uri, 'api_version': api_version}, timeout=900)
        auth_url = f'https://www.facebook.com/{api_version}/dialog/oauth?'+ urllib.parse.urlencode({
            'client_id': app_id,
            'redirect_uri': redirect_uri,
            'state': state,
            'response_type': 'code',
            'scope': ','.join(scopes),
        })
        return Response({'auth_url': auth_url, 'state': state, 'redirect_uri': redirect_uri})


class PoolAccountFacebookOAuthCallback(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='账号池 Facebook OAuth2 回调（保存 token 到 PoolAccount）', tags=['账号池'])
    def get(self, request):
        state = request.query_params.get('state')
        code = request.query_params.get('code')
        ctx = cache.get(f'pool:fb:{state}')
        if not ctx:
            return Response({'detail': 'state 无效或过期'}, status=400)
        cache.delete(f'pool:fb:{state}')
        app_id = ctx.get('app_id')
        app_secret = ctx.get('app_secret')
        redirect_uri = ctx.get('redirect_uri')
        api_version = ctx.get('api_version') or 'v19.0'
        token_url = f'https://graph.facebook.com/{api_version}/oauth/access_token'
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
        acc = PoolAccount.objects.create(
            provider='facebook',
            name=f"fb-{timezone.now().strftime('%Y%m%d-%H%M%S')}",
            api_key=app_id,
            api_secret=app_secret,
            is_ban=False,
            status='active',
        )
        if access_token:
            acc.set_access_token(access_token)
        acc.save()
        return Response({'status': 'ok', 'pool_account_id': acc.id})
