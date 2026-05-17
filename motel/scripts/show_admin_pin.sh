#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi
EFFECTIVE_PIN="${MOTEL_ADMIN_PIN:-${MOTEL_KIOSK_TEST_PIN:-2468}}"
SOURCE="default (2468)"
if [ -n "${MOTEL_ADMIN_PIN:-}" ]; then
  SOURCE="MOTEL_ADMIN_PIN"
elif [ -n "${MOTEL_KIOSK_TEST_PIN:-}" ]; then
  SOURCE="MOTEL_KIOSK_TEST_PIN"
fi
echo "Effective admin PIN: $EFFECTIVE_PIN"
echo "Source: $SOURCE"
