import os
import sys

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Mark jobs not updated in the given number of days (default 30) as inactive."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=30,
            help="Jobs whose updated_at is older than this many days are deactivated.",
        )

    def handle(self, *args, **options):
        root = str(settings.BASE_DIR.parent)
        if root not in sys.path:
            sys.path.append(root)

        from tasks.pipeline import deactivate_stale_jobs

        days = options["days"]
        result = deactivate_stale_jobs(days=days)  # run synchronously; it's a single UPDATE
        self.stdout.write(self.style.SUCCESS(
            f"Deactivated {result['deactivated']} jobs not updated in {days} days."
        ))
