from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, GroupViewSet, PermissionViewSet, AuditLogViewSet, LoginAPIView, RegisterAPIView, ChangePasswordAPIView, LogoutAPIView, LogoutAllAPIView, AdminChangePasswordAPIView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'roles', GroupViewSet)
router.register(r'permissions', PermissionViewSet)
router.register(r'audit-logs', AuditLogViewSet, basename='auditlog')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/login/', LoginAPIView.as_view(), name='accounts-login'),
    path('auth/register/', RegisterAPIView.as_view(), name='accounts-register'),
    path('auth/change-password/', ChangePasswordAPIView.as_view(), name='accounts-change-password'),
    path('auth/admin/change-password/', AdminChangePasswordAPIView.as_view(), name='accounts-admin-change-password'),
    path('auth/logout/', LogoutAPIView.as_view(), name='accounts-logout'),
    path('auth/logout-all/', LogoutAllAPIView.as_view(), name='accounts-logout-all'),
    # JWT auth endpoints
    path('auth/jwt/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/jwt/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/jwt/verify/', TokenVerifyView.as_view(), name='token_verify'),
]


