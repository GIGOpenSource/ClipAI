from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PoolAccountViewSet,
    PoolAccountTwitterOAuthStart, PoolAccountTwitterOAuthCallback,
    PoolAccountFacebookOAuthStart, PoolAccountFacebookOAuthCallback,
)

router = DefaultRouter()
router.register(r'pool-accounts', PoolAccountViewSet)

urlpatterns = [
    path('', include(router.urls)),
    # OAuth for PoolAccount (account pool)
    path('oauth/pool/twitter/start/', PoolAccountTwitterOAuthStart.as_view(), name='pool-twitter-oauth-start'),
    path('oauth/pool/twitter/callback/', PoolAccountTwitterOAuthCallback.as_view(), name='pool-twitter-oauth-callback'),
    path('oauth/pool/facebook/start/', PoolAccountFacebookOAuthStart.as_view(), name='pool-facebook-oauth-start'),
    path('oauth/pool/facebook/callback/', PoolAccountFacebookOAuthCallback.as_view(), name='pool-facebook-oauth-callback'),
]

urlpatterns += []


