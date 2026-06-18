import os
import sys
import django
import hashlib

sys.path.append(os.path.join(os.path.dirname(__file__), "../backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "job_hunt.settings")
django.setup()

from django.test import RequestFactory
from jobs.views import JobViewSet
from jobs.models import Job

# Clean any existing test jobs
Job.objects.filter(company="NormalizationTestCompany").delete()

factory = RequestFactory()
view = JobViewSet.as_view({'post': 'bulk_create'})

# Job 1 with tracking parameters
job_data_1 = {
    "url": "https://www.linkedin.com/jobs/view/999999999/?refId=123456&trackingId=abcdef",
    "title": "Software Engineer (URL Normalize Test)",
    "company": "NormalizationTestCompany",
    "source": "linkedin",
    "is_formatted": True
}

request_1 = factory.post("/api/jobs/bulk_create/", [job_data_1], content_type="application/json")
response_1 = view(request_1)
print(f"First request response status: {response_1.status_code}")
print(f"First request response data: {response_1.data}")

# Job 2 with DIFFERENT tracking parameters
job_data_2 = {
    "url": "https://www.linkedin.com/jobs/view/999999999/?refId=789012&trackingId=ghijkl",
    "title": "Software Engineer (URL Normalize Test)",
    "company": "NormalizationTestCompany",
    "source": "linkedin",
    "is_formatted": True
}

request_2 = factory.post("/api/jobs/bulk_create/", [job_data_2], content_type="application/json")
response_2 = view(request_2)
print(f"Second request response status: {response_2.status_code}")
print(f"Second request response data: {response_2.data}")

# Check database
jobs = Job.objects.filter(company="NormalizationTestCompany")
print(f"Jobs in database: {jobs.count()}")
for j in jobs:
    print(f"ID: {j.id} | URL: {j.url} | Hash: {j.url_hash} | Alert: {j.alert_sent}")

# Clean up
Job.objects.filter(company="NormalizationTestCompany").delete()
