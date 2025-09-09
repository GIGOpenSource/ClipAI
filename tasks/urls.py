from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ScheduledTaskViewSet, TaskRunViewSet

router = DefaultRouter()
router.register(r'scheduled', ScheduledTaskViewSet)
router.register(r'runs', TaskRunViewSet, basename='taskruns')

urlpatterns = [
    path('', include(router.urls)),
]


