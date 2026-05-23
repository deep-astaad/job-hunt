from rest_framework.routers import DefaultRouter
from .views import JobViewSet, JobRankingViewSet

router = DefaultRouter()
router.register(r"jobs", JobViewSet)
router.register(r"rankings", JobRankingViewSet)

urlpatterns = router.urls
