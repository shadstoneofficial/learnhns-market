#!/bin/bash
set -e

echo "Starting Deployment Process..."

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
