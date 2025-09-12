from django.urls import path
from .views import SummaryView, BreakdownProviderView, BreakdownTypeView, OverviewView, OverviewExportView, RebuildNowView

urlpatterns = [
    path('summary/', SummaryView.as_view()),
    path('breakdown/provider/', BreakdownProviderView.as_view()),
    path('breakdown/type/', BreakdownTypeView.as_view()),
    path('overview/', OverviewView.as_view()),
    path('overview/export/', OverviewExportView.as_view()),
    path('rebuild/', RebuildNowView.as_view()),
]


