#!/bin/bash
set -e

echo "Starting Deployment Process..."

if [ "$PROCESS_TYPE" = "expiring-watcher" ]; then
    echo "Starting Expiring Name Watcher..."
    exec python scripts/watch-global-expiring-names.py \
        --poll-seconds "${WATCHER_POLL_SECONDS:-60}" \
        --batch-size "${WATCHER_BATCH_SIZE:-10}"
fi

if [ "$PROCESS_TYPE" = "renewal-alerts" ]; then
    echo "Running Renewal Alert Worker..."
    exec python scripts/send-renewal-alerts.py \
        --limit "${ALERT_WORKER_LIMIT:-500}"
fi

# 1. Run Database Migrations
echo "Running Database Migrations..."
flask db upgrade

# 2. Start the Gunicorn Server
echo "Starting Gunicorn Server..."
exec gunicorn wsgi:app \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --timeout 120 \
    --log-level info
