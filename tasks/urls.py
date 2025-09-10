from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ScheduledTaskViewSet, TaskRunViewSet, TagViewSet, TagTemplateViewSet

router = DefaultRouter()
router.register(r'scheduled', ScheduledTaskViewSet)
router.register(r'runs', TaskRunViewSet, basename='taskruns')
router.register(r'tags', TagViewSet)
router.register(r'tag-templates', TagTemplateViewSet)

urlpatterns = [
    path('', include(router.urls)),
]


