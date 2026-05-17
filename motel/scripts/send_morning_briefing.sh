#!/bin/bash
set -e

PROJECT_HOME="/home/webemo-aaron/projects/webemo-hermes-agent"
HERMES_HOME="$PROJECT_HOME/.hermes-west-bethel"
LOG_FILE="/tmp/morning_briefing.log"
API_URL="http://localhost:8653"

echo "[$(date)] ═══════════════════════════════════════════" >> "$LOG_FILE"
echo "[$(date)] Starting morning briefing routine" >> "$LOG_FILE"

# Check if Marvin is running
if ! pgrep -f "hermes.*\.hermes-west-bethel" > /dev/null; then
    echo "[$(date)] Marvin not running, starting..." >> "$LOG_FILE"
    cd "$PROJECT_HOME"
    export HERMES_HOME="$HERMES_HOME"
    nohup python cli.py > /dev/null 2>&1 &
    sleep 3
fi

# Check if REST API is running
max_retries=5
retry_count=0
while [ $retry_count -lt $max_retries ]; do
    if curl -s "$API_URL/api/motel/desk-overview" > /dev/null 2>&1; then
        echo "[$(date)] REST API is responding" >> "$LOG_FILE"
        break
    fi
    retry_count=$((retry_count + 1))
    if [ $retry_count -lt $max_retries ]; then
        echo "[$(date)] REST API not ready yet, waiting... (attempt $retry_count/$max_retries)" >> "$LOG_FILE"
        sleep 2
    fi
done

if [ $retry_count -eq $max_retries ]; then
    echo "[$(date)] ❌ REST API not responding after $max_retries attempts" >> "$LOG_FILE"
    exit 1
fi

# Fetch data via REST API
echo "[$(date)] Fetching briefing data..." >> "$LOG_FILE"

DESK_OVERVIEW=$(curl -s "$API_URL/api/motel/desk-overview" 2>/dev/null || echo '{}')
DASHBOARD_STATS=$(curl -s "$API_URL/api/motel/dashboard-stats" 2>/dev/null || echo '{}')
TODAY_DATE=$(date +%Y-%m-%d)
TODAY_BOOKINGS=$(curl -s "$API_URL/api/motel/bookings?date=$TODAY_DATE" 2>/dev/null || echo '[]')

# Parse data with jq (with fallbacks)
OCCUPANCY=$(echo "$DASHBOARD_STATS" | jq -r '.occupancy_percentage // "N/A"' 2>/dev/null || echo "N/A")
ARRIVALS=$(echo "$TODAY_BOOKINGS" | jq '[.[] | select(.status=="arriving")] | length' 2>/dev/null || echo "0")
DEPARTURES=$(echo "$TODAY_BOOKINGS" | jq '[.[] | select(.status=="departing")] | length' 2>/dev/null || echo "0")
ALERTS=$(echo "$DESK_OVERVIEW" | jq -r '.unresolved_alerts // 0' 2>/dev/null || echo "0")
WORK_ORDERS=$(echo "$DESK_OVERVIEW" | jq -r '.open_work_orders // 0' 2>/dev/null || echo "0")
REVENUE=$(echo "$DASHBOARD_STATS" | jq -r '.revenue_today // "$0.00"' 2>/dev/null || echo "$0.00")

echo "[$(date)] Data parsed: Occupancy=$OCCUPANCY, Arrivals=$ARRIVALS, Departures=$DEPARTURES, Alerts=$ALERTS, WO=$WORK_ORDERS" >> "$LOG_FILE"

# Build message
MESSAGE="🌅 *Morning Briefing — $(date '+%a, %b %d, %Y')*

📊 *Status*
• Occupancy: $OCCUPANCY
• Today's Arrivals: $ARRIVALS
• Today's Departures: $DEPARTURES

💰 Revenue Today: $REVENUE

⚠️ *Alerts*: $ALERTS unresolved

🔧 *Work Orders*: $WORK_ORDERS open

Ask me for details: \`What's the current desk overview?\`"

# Send via Telegram if configured
if [ -f "$HERMES_HOME/.env" ]; then
    TELEGRAM_BOT_TOKEN=$(grep "TELEGRAM_BOT_TOKEN" "$HERMES_HOME/.env" 2>/dev/null | cut -d'=' -f2 | tr -d ' ' | tr -d '"' || echo "")
    TELEGRAM_CHAT_ID=$(grep "TELEGRAM_CHAT_ID" "$HERMES_HOME/.env" 2>/dev/null | cut -d'=' -f2 | tr -d ' ' | tr -d '"' || echo "")

    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        echo "[$(date)] Sending Telegram message..." >> "$LOG_FILE"
        RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
            -d "chat_id=$TELEGRAM_CHAT_ID" \
            -d "text=$MESSAGE" \
            -d "parse_mode=Markdown" 2>/dev/null || echo '{"ok":false}')

        OK=$(echo "$RESPONSE" | jq -r '.ok // false' 2>/dev/null || echo "false")
        if [ "$OK" = "true" ]; then
            echo "[$(date)] ✅ Briefing sent via Telegram" >> "$LOG_FILE"
        else
            echo "[$(date)] ❌ Telegram send failed: $RESPONSE" >> "$LOG_FILE"
        fi
    else
        echo "[$(date)] ⚠️  Telegram credentials not configured in .env" >> "$LOG_FILE"
    fi
else
    echo "[$(date)] ⚠️  .env file not found" >> "$LOG_FILE"
fi

echo "[$(date)] Morning briefing routine complete" >> "$LOG_FILE"
echo "[$(date)] ═══════════════════════════════════════════" >> "$LOG_FILE"
