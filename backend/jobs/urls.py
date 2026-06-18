from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import JobViewSet, JobRankingViewSet, SettingsAPIView
from .api_views import (
    BrowseView,
    ProfilesView,
    DashboardView,
    DashboardAlertView,
    TriggerScrapeView,
    TriggerProcessingView,
)

router = DefaultRouter()
router.register(r"jobs", JobViewSet)
router.register(r"rankings", JobRankingViewSet)

urlpatterns = router.urls + [
    path("settings/", SettingsAPIView.as_view(), name="settings-api"),
    # New endpoints for Next.js frontend
    path("browse/", BrowseView.as_view(), name="browse"),
    path("profiles/", ProfilesView.as_view(), name="profiles"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard/alert/", DashboardAlertView.as_view(), name="dashboard-alert"),
    path("pipeline/trigger-scrape/", TriggerScrapeView.as_view(), name="trigger-scrape"),
    path("pipeline/trigger-processing/", TriggerProcessingView.as_view(), name="trigger-processing"),
]
