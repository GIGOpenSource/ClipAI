from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SimpleTaskViewSet

router = DefaultRouter()
router.register(r'simple', SimpleTaskViewSet)

urlpatterns = [
    path('', include(router.urls)),
]


