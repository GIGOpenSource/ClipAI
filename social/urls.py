from django.urls import path, include
from django.conf import settings
from .views import WebhookReceiver, SocialAccountHealthView, TwitterOAuthStart, TwitterOAuthCallback, FacebookOAuthStart, FacebookOAuthCallback, InstagramOAuthStart, InstagramOAuthCallback
from rest_framework.routers import DefaultRouter
from .views import SocialConfigViewSet, SocialAccountViewSet

router = DefaultRouter()
router.register(r'configs', SocialConfigViewSet)
router.register(r'accounts', SocialAccountViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('accounts/health-check/', SocialAccountHealthView.as_view(), name='social-accounts-health-check'),
    path('oauth/twitter/start/', TwitterOAuthStart.as_view(), name='twitter-oauth-start'),
    path('oauth/twitter/callback/', TwitterOAuthCallback.as_view(), name='twitter-oauth-callback'),
    path('oauth/twitter/callback/<int:user_id>/', TwitterOAuthCallback.as_view(), name='twitter-oauth-callback-user'),
    path('oauth/facebook/start/', FacebookOAuthStart.as_view(), name='facebook-oauth-start'),
    path('oauth/facebook/callback/', FacebookOAuthCallback.as_view(), name='facebook-oauth-callback'),
    path('oauth/facebook/callback/<int:user_id>/', FacebookOAuthCallback.as_view(), name='facebook-oauth-callback-user'),
    path('oauth/instagram/start/', InstagramOAuthStart.as_view(), name='instagram-oauth-start'),
    path('oauth/instagram/callback/', InstagramOAuthCallback.as_view(), name='instagram-oauth-callback'),
    path('oauth/instagram/callback/<int:user_id>/', InstagramOAuthCallback.as_view(), name='instagram-oauth-callback-user'),
]

if getattr(settings, 'WEBHOOKS_ENABLED', False):
    urlpatterns += [
        path('webhooks/<str:provider>/', WebhookReceiver.as_view(), name='webhook-receiver'),
    ]


