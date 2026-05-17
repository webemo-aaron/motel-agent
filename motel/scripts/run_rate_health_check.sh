#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/webemo-aaron/projects/webemo-hermes-agent"
LOG_DIR="$ROOT/motel/data/logs"
OUT_DIR="$ROOT/motel/data"
STATUS_FILE="$OUT_DIR/competitor_rate_pipeline_health.json"
NOW_EPOCH=$(date -u +%s)

mkdir -p "$LOG_DIR" "$OUT_DIR"

check_log_ok() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  grep -q "Rows written:" "$f" || return 1
  if grep -Eiq "Traceback|Exception:|ERROR:|No such file or directory" "$f"; then
    return 1
  fi
  return 0
}

latest_file() {
  local pattern="$1"
  ls -1t $LOG_DIR/$pattern 2>/dev/null | head -n 1 || true
}

latest_valid_file() {
  local pattern="$1"
  local f
  for f in $(ls -1t $LOG_DIR/$pattern 2>/dev/null || true); do
    if check_log_ok "$f"; then
      echo "$f"
      return 0
    fi
  done
  echo ""
}

file_age_hours() {
  local f="$1"
  if [[ -z "${f:-}" || ! -f "$f" ]]; then
    echo 999999
    return
  fi
  local m
  m=$(date -u -r "$f" +%s)
  echo $(( (NOW_EPOCH - m) / 3600 ))
}

full_latest=$(latest_file 'rates_full_*.log')
winter_latest=$(latest_file 'rates_winter_*.log')
weekend_latest=$(latest_file 'rates_weekend_deep_*.log')

full=$(latest_valid_file 'rates_full_*.log')
winter=$(latest_valid_file 'rates_winter_*.log')
weekend=$(latest_valid_file 'rates_weekend_deep_*.log')

full_age=$(file_age_hours "$full")
winter_age=$(file_age_hours "$winter")
weekend_age=$(file_age_hours "$weekend")

full_ok=false; [[ -n "$full" ]] && full_ok=true
winter_ok=false; [[ -n "$winter" ]] && winter_ok=true
weekend_ok=false; [[ -n "$weekend" ]] && weekend_ok=true

fresh_full=false; [[ "$full_age" -le 48 ]] && fresh_full=true
fresh_winter=false; [[ "$winter_age" -le 24 ]] && fresh_winter=true
fresh_weekend=false; [[ "$weekend_age" -le 168 ]] && fresh_weekend=true

healthy=true
[[ "$full_ok" == true && "$fresh_full" == true ]] || healthy=false
[[ "$winter_ok" == true && "$fresh_winter" == true ]] || healthy=false
[[ "$weekend_ok" == true && "$fresh_weekend" == true ]] || healthy=false

cat > "$STATUS_FILE" <<JSON
{
  "timestamp_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "healthy": ${healthy},
  "checks": {
    "full": {"latest": "${full_latest}", "last_valid": "${full}", "age_hours": ${full_age}, "valid": ${full_ok}, "fresh": ${fresh_full}},
    "winter": {"latest": "${winter_latest}", "last_valid": "${winter}", "age_hours": ${winter_age}, "valid": ${winter_ok}, "fresh": ${fresh_winter}},
    "weekend_deep": {"latest": "${weekend_latest}", "last_valid": "${weekend}", "age_hours": ${weekend_age}, "valid": ${weekend_ok}, "fresh": ${fresh_weekend}}
  }
}
JSON

if [[ "$healthy" == true ]]; then
  echo "RATE_PIPELINE_HEALTH=OK"
  exit 0
fi

echo "RATE_PIPELINE_HEALTH=FAIL"
if [[ -n "${RATE_HEALTH_ALERT_CMD:-}" ]]; then
  bash -lc "$RATE_HEALTH_ALERT_CMD"
fi
exit 2
