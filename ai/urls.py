from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AIConfigViewSet

router = DefaultRouter()
router.register(r'configs', AIConfigViewSet)

urlpatterns = [
    path('', include(router.urls)),
]


