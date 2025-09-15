from django.urls import path
from .views import SummaryView, OverviewView

urlpatterns = [
    path('summary/', SummaryView.as_view()),
    path('overview/', OverviewView.as_view()),
]


