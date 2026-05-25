import os
import sys

# Ensure project root is on Python path for task autodiscovery
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from celery import Celery
from config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

app = Celery('job_hunt')

app.config_from_object({
    'broker_url': CELERY_BROKER_URL,
    'result_backend': CELERY_RESULT_BACKEND,
    'task_serializer': 'json',
    'result_serializer': 'json',
    'accept_content': ['json'],
    'task_track_started': True,
    'task_acks_late': True,
    'worker_prefetch_multiplier': 1,
    'task_soft_time_limit': 18000,
    'task_time_limit': 18300,
})

# Explicitly import task modules to register tasks with the worker.
# autodiscover_tasks(['tasks']) looks for a `tasks.tasks` submodule by default,
# which doesn't exist here — our tasks live in pipeline/scraping/formatting/ranking.
# These imports come after `app` is defined, so no circular import issue.
import tasks.pipeline  # noqa: F401
import tasks.scraping  # noqa: F401
import tasks.formatting  # noqa: F401
import tasks.ranking  # noqa: F401
