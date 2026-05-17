#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/webemo-aaron/projects/webemo-hermes-agent"
LOG_DIR="$ROOT/motel/data/logs"
mkdir -p "$LOG_DIR"
TS=$(date -u +"%Y%m%dT%H%M%SZ")
"$ROOT/motel/scripts/rate_aggregation_v2.py" --query-timeout 7 --max-properties 8 --only-tag winter_weekend_package --max-dates 10 > "$LOG_DIR/rates_winter_${TS}.log" 2>&1
