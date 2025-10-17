from django.urls import path, include
from rest_framework.routers import DefaultRouter

from stats.views import CollectArticalView
from .views import SimpleTaskViewSet, TaskTagsView, GlobalTagsView, SimpleTaskRunViewSet, TaskLogView, \
    TaskSchedulerView

router = DefaultRouter()
router.register(r'simple', SimpleTaskViewSet)
router.register(r'task_log', SimpleTaskRunViewSet, basename='task_log')


urlpatterns = [
    path('', include(router.urls)),
    path('tags/global/', GlobalTagsView.as_view(), name='all-tags'),
    path('<int:task_id>/tags/', TaskTagsView.as_view(), name='task-tags'),
    path('log_detail/', TaskLogView.as_view(), name='task-log'),
    path('collect-tweets/', CollectArticalView.as_view(), name='collect-tweets'),
    # path('schedule-task/', TaskSchedulerView.as_view(), name='schedule-task'),
    # 定时任务暂停、恢复、删除
    path('simple/<int:task_id>/schedule/', TaskSchedulerView.as_view(), name='task-pause'),
]


