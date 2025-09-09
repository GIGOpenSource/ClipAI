from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import KeywordConfigViewSet

router = DefaultRouter()
router.register(r'configs', KeywordConfigViewSet)

urlpatterns = [
    path('', include(router.urls)),
]


