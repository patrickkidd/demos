#!/bin/bash
set -e
python /app/scripts/init_data.py
mkdir -p /home/app/.claude
python /app/scripts/watchdog.py &
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
