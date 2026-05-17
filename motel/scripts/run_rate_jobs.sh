#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/webemo-aaron/projects/webemo-hermes-agent"
LOG_DIR="$ROOT/motel/data/logs"
mkdir -p "$LOG_DIR"

TS=$(date -u +"%Y%m%dT%H%M%SZ")

# Weekly full seasonal/event-aware refresh (2 years, controlled date chunk)
"$ROOT/motel/scripts/rate_aggregation_v2.py" --max-dates 60   > "$LOG_DIR/rates_full_${TS}.log" 2>&1

# Daily winter package monitoring (Fri/Sat Dec-Mar logic)
"$ROOT/motel/scripts/rate_aggregation_v2.py" --only-tag winter_weekend_package --max-dates 30   > "$LOG_DIR/rates_winter_${TS}.log" 2>&1

# Optional: keep a latest symlink-like pointer by copying
cp "$ROOT/motel/data/competitor_rates_v2_latest.csv" "$ROOT/motel/data/competitor_rates_latest_snapshot.csv"
