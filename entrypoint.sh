#!/bin/bash
set -e

APP_MODE="${APP_MODE:-web}"

case "$APP_MODE" in
  web)
    echo "Starting Django backend..."
    cd /app/backend
    python manage.py migrate --noinput
    # --insecure: DEBUG is False here, and runserver otherwise refuses to
    # serve /static/* (admin's own CSS/JS), leaving the admin UI unstyled.
    # Django's docs call this flag safe specifically for that case since it
    # only affects the staticfiles app, not application routes.
    exec python manage.py runserver 0.0.0.0:8000 --insecure
    ;;
  job-finder)
    echo "Running job finder pipeline..."
    cd /app
    exec python main.py
    ;;
  celery-worker)
    echo "Starting Celery worker..."
    cd /app
    if [ $# -gt 0 ]; then
      exec "$@"
    else
      exec celery -A celery_app worker --loglevel=info --concurrency=4
    fi
    ;;
  celery-beat)
    echo "Starting Celery beat..."
    cd /app
    if [ $# -gt 0 ]; then
      exec "$@"
    else
      exec celery -A celery_app beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    fi
    ;;
  celery-flower)
    echo "Starting Celery flower..."
    cd /app
    if [ $# -gt 0 ]; then
      exec "$@"
    else
      exec celery -A celery_app flower --port=5555
    fi
    ;;
  *)
    echo "Unknown APP_MODE: $APP_MODE"
    echo "Valid modes: web, job-finder, celery-worker, celery-beat, celery-flower"
    exit 1
    ;;
esac
