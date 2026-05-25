from django.urls import path
from . import web_views

app_name = "jobs_web"

urlpatterns = [
    path("", web_views.dashboard, name="dashboard"),
    path("trigger-scrape/", web_views.trigger_scrape, name="trigger_scrape"),
]
