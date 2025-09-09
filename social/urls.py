from django.urls import path, include
from django.conf import settings
from .views import WebhookReceiver, SocialAccountHealthView, TwitterOAuthStart, TwitterOAuthCallback, TwitterMeOAuth1, FacebookOAuthStart, FacebookOAuthCallback, InstagramOAuthStart, InstagramOAuthCallback
from rest_framework.routers import DefaultRouter
from .views import SocialConfigViewSet

router = DefaultRouter()
router.register(r'configs', SocialConfigViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('accounts/health-check/', SocialAccountHealthView.as_view(), name='social-accounts-health-check'),
    path('oauth/twitter/start/', TwitterOAuthStart.as_view(), name='twitter-oauth-start'),
    path('oauth/twitter/callback/', TwitterOAuthCallback.as_view(), name='twitter-oauth-callback'),
    path('oauth/twitter/me', TwitterMeOAuth1.as_view(), name='twitter-me-oauth1'),
    path('oauth/facebook/start/', FacebookOAuthStart.as_view(), name='facebook-oauth-start'),
    path('oauth/facebook/callback/', FacebookOAuthCallback.as_view(), name='facebook-oauth-callback'),
    path('oauth/instagram/start/', InstagramOAuthStart.as_view(), name='instagram-oauth-start'),
    path('oauth/instagram/callback/', InstagramOAuthCallback.as_view(), name='instagram-oauth-callback'),
]

if getattr(settings, 'WEBHOOKS_ENABLED', False):
    urlpatterns += [
        path('webhooks/<str:provider>/', WebhookReceiver.as_view(), name='webhook-receiver'),
    ]


