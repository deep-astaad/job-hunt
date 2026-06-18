import os
import sys
import django

sys.path.append(os.path.join(os.path.dirname(__file__), "../backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "job_hunt.settings")
django.setup()

from jobs.models import Job

# Get TokyoDev jobs
tokyodev_jobs = Job.objects.filter(source__icontains="tokyo").order_by("-scraped_at")

print(f"Total TokyoDev jobs: {tokyodev_jobs.count()}")

urls = []
for job in tokyodev_jobs[:20]:
    print(f"ID: {job.id} | Title: {job.title} | URL: {job.url} | Scraped: {job.scraped_at} | Alert: {job.alert_sent}")
    urls.append(job.url)

print("\nDuplicate URLs:")
from collections import Counter
url_counts = Counter([j.url for j in tokyodev_jobs])
for url, count in url_counts.items():
    if count > 1:
        print(f"{url} -> {count}")
