from django.urls import path
from .views import SummaryView, OverviewView, DetailView

urlpatterns = [
    path('summary/', SummaryView.as_view()),
    path('detail/', DetailView.as_view()),
    path('overview/', OverviewView.as_view()),
]


