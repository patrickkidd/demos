#!/bin/bash
set -e
python /app/scripts/init_data.py
[ ! -f /instance/allsides_bias.csv ] && cp /app/data/allsides_bias.csv /instance/allsides_bias.csv
mkdir -p /home/app/.claude
python /app/scripts/watchdog.py &
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
