from django.urls import path, include
from rest_framework.routers import DefaultRouter

from stats.views import CollectArticalView
from .views import SimpleTaskViewSet, TaskTagsView, GlobalTagsView

router = DefaultRouter()
router.register(r'simple', SimpleTaskViewSet)


urlpatterns = [
    path('', include(router.urls)),
    path('tags/global/', GlobalTagsView.as_view(), name='all-tags'),
    path('<int:task_id>/tags/', TaskTagsView.as_view(), name='task-tags'),
    path('collect-tweets/', CollectArticalView.as_view(), name='collect-tweets'),

]


