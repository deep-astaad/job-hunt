import os
import sys

# Add the project root to sys.path so Django can import celery_app and tasks
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from celery_app import app as celery_app

__all__ = ('celery_app',)