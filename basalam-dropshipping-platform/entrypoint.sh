#!/bin/sh
set -e

# Flexible entrypoint for running different services from the same image.
# Usage: SERVICE=api|worker|scheduler|consumer ./entrypoint.sh
#
# If SERVICE is not set, falls back to CMD args (or default uvicorn).

SERVICE="${SERVICE:-}"

case "$SERVICE" in
    api)
        exec uvicorn src.main:app \
            --host 0.0.0.0 \
            --port "${PORT:-8000}" \
            --workers "${UVICORN_WORKERS:-1}" \
            --loop uvloop \
            --no-access-log
        ;;
    worker)
        exec celery -A src.workers.celery_config:celery_app worker \
            --loglevel="${LOG_LEVEL:-info}" \
            --concurrency="${CELERY_CONCURRENCY:-4}" \
            --max-tasks-per-child="${CELERY_MAX_TASKS_PER_CHILD:-1000}"
        ;;
    scheduler)
        exec celery -A src.workers.celery_config:celery_app beat \
            --loglevel="${LOG_LEVEL:-info}" \
            --scheduler celery.beat.PersistentScheduler
        ;;
    consumer)
        exec python -m scripts.run_consumers
        ;;
    *)
        # Default: run whatever CMD was passed
        exec "$@"
        ;;
esac
