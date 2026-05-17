#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes-webemo-hermes-agent}"
export MOTEL_KIOSK_PORT="${MOTEL_KIOSK_PORT:-5182}"
export MOTEL_HERMES_PORT="${MOTEL_HERMES_PORT:-8652}"
export MOTEL_API_PORT="${MOTEL_API_PORT:-8653}"
export MOTEL_CODEX_PORT="${MOTEL_CODEX_PORT:-8654}"
export VOICE_BRIDGE_PORT="${VOICE_BRIDGE_PORT:-8655}"
export API_SERVER_HOST="${API_SERVER_HOST:-127.0.0.1}"
export API_SERVER_PORT="$MOTEL_HERMES_PORT"
export API_SERVER_KEY="${API_SERVER_KEY:-test-key-for-local-development}"
export HERMES_API_KEY="${HERMES_API_KEY:-sk-motel-dev-agent}"
export HERMES_GATEWAY_SKIP_SERVICE_REFRESH=1


require_free_port() {
  local port="$1"
  local name="$2"
  if lsof -iTCP:"$port" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
    echo "✗ Port $port already in use ($name)."
    echo "  Stop existing service or change $name port env before starting full stack."
    lsof -iTCP:"$port" -sTCP:LISTEN -n -P || true
    exit 1
  fi
}

require_free_port "$MOTEL_API_PORT" "MOTEL_API_PORT"
require_free_port "$MOTEL_HERMES_PORT" "MOTEL_HERMES_PORT"
require_free_port "$MOTEL_CODEX_PORT" "MOTEL_CODEX_PORT"
require_free_port "$MOTEL_KIOSK_PORT" "MOTEL_KIOSK_PORT"

cd "$REPO_ROOT"
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi
source .venv/bin/activate
PYTHON="$REPO_ROOT/.venv/bin/python"

if [ ! -f "$HERMES_HOME/config.yaml" ]; then
  mkdir -p "$HERMES_HOME"
  cp "$REPO_ROOT/.hermes-west-bethel/config.yaml" "$HERMES_HOME/config.yaml"
  cp "$REPO_ROOT/.hermes-west-bethel/SOUL.md" "$HERMES_HOME/SOUL.md"
  cp "$REPO_ROOT/.hermes-west-bethel/.env.example" "$HERMES_HOME/.env.example"
fi

echo "Starting West Bethel Motel Agent"
echo "  HERMES_HOME:  $HERMES_HOME"
echo "  API server:   http://localhost:$MOTEL_API_PORT"
echo "  Hermes agent: http://localhost:$MOTEL_HERMES_PORT"
echo "  Voice bridge: ws://localhost:$VOICE_BRIDGE_PORT"
echo "  Codex agent:  http://localhost:$MOTEL_CODEX_PORT"
echo "  Kiosk UI:     http://localhost:$MOTEL_KIOSK_PORT"
MOTEL_ADMIN_PIN_EFFECTIVE="${MOTEL_ADMIN_PIN:-${MOTEL_KIOSK_TEST_PIN:-2468}}"
if [ -n "${MOTEL_ADMIN_PIN:-}" ]; then
  echo "  Admin PIN source: MOTEL_ADMIN_PIN"
elif [ -n "${MOTEL_KIOSK_TEST_PIN:-}" ]; then
  echo "  Admin PIN source: MOTEL_KIOSK_TEST_PIN"
else
  echo "  Admin PIN source: default (2468)"
fi
echo ""

# Seed database with test data (if not already seeded)
echo "Checking database..."
"$PYTHON" -c "from motel.scripts.seed_database import seed_database; seed_database()"

# Motel REST API (kiosk reads)
"$PYTHON" -m motel.api &
API_PID=$!
echo "  motel/api.py started (PID $API_PID)"

# Voice bridge (Twilio ConversationRelay WebSocket adapter)
if ! "$PYTHON" -m motel.voice_bridge > /tmp/voice_bridge.log 2>&1 &
then
  echo "⚠️  Voice bridge failed to start (check /tmp/voice_bridge.log)"
else
  VOICE_BRIDGE_PID=$!
  echo "  voice_bridge.py started (PID $VOICE_BRIDGE_PID)"
fi

# Hermes gateway: Telegram + OpenAI-compatible API
"$PYTHON" -m hermes_cli.main gateway run --replace &
GATEWAY_PID=$!
echo "  Hermes gateway started (PID $GATEWAY_PID)"

# Codex HTTP wrapper for kiosk agent chat
"$PYTHON" -m motel.codex_server &
CODEX_PID=$!
echo "  Codex wrapper started (PID $CODEX_PID)"

# Kiosk UI (Chromium kiosk mode can point to localhost:$MOTEL_KIOSK_PORT)
cd "$REPO_ROOT/motel/kiosk"
npm run dev &
KIOSK_PID=$!
echo "  Kiosk UI started (PID $KIOSK_PID)"

echo ""
echo "  All services running. Ctrl+C to stop."

cleanup() {
  echo "Stopping..."
  kill "$API_PID" "$GATEWAY_PID" "$CODEX_PID" "$KIOSK_PID" "${VOICE_BRIDGE_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
wait
