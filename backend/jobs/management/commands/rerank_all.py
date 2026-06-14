import os
import sys

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Re-rank every formatted job (including already-ranked ones) to backfill "
        "the raw llm_tier field. Dispatches to Celery. Costs OpenAI credits."
    )

    def handle(self, *args, **options):
        # The pipeline tasks live at the repo root, not inside the Django app.
        root = str(settings.BASE_DIR.parent)
        if root not in sys.path:
            sys.path.append(root)

        from tasks.pipeline import rerank_all_jobs_task

        result = rerank_all_jobs_task.delay()
        self.stdout.write(self.style.SUCCESS(
            f"Dispatched re-rank task (id={result.id}). "
            "Watch the celery-worker logs for progress."
        ))
