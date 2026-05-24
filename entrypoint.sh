#!/bin/bash
set -e

APP_MODE="${APP_MODE:-web}"

case "$APP_MODE" in
  web)
    echo "Starting Django backend..."
    cd /app/backend
    python manage.py migrate --noinput
    exec python manage.py runserver 0.0.0.0:8000
    ;;
  job-finder)
    echo "Running job finder pipeline..."
    cd /app
    exec python main.py
    ;;
  *)
    echo "Unknown APP_MODE: $APP_MODE"
    echo "Valid modes: web, job-finder"
    exit 1
    ;;
esac
