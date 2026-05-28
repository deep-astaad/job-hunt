from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import JobViewSet, JobRankingViewSet, SettingsAPIView

router = DefaultRouter()
router.register(r"jobs", JobViewSet)
router.register(r"rankings", JobRankingViewSet)

urlpatterns = router.urls + [
    path('settings/', SettingsAPIView.as_view(), name='settings-api'),
]
