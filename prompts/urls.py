from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PromptConfigViewSet

router = DefaultRouter()
router.register(r'configs', PromptConfigViewSet)

urlpatterns = [
    path('', include(router.urls)),
]


