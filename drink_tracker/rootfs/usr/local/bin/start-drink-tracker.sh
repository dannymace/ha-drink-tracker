#!/usr/bin/with-contenv bashio
set -euo pipefail

export DRINK_TRACKER_CONFIG_PATH="/data/options.json"
export DRINK_TRACKER_DATA_DIR="/data"
export DRINK_TRACKER_SUPERVISOR_URL="${SUPERVISOR_URL:-http://supervisor}"
export PYTHONPATH="/opt/drink-tracker/app"

bashio::log.info "Starting Drink Tracker"

exec python3 -m uvicorn drink_tracker.main:app --host 0.0.0.0 --port 8099
