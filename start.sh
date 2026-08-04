#!/usr/bin/env bash
# Start both services (WhatsApp gateway + core) from anywhere.
#
#   ./start.sh          start both, stream the logs
#   ./start.sh stop     stop both
#   ./start.sh status    health check
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY="$ROOT/services/whatsapp_gateway"
LOGS="$ROOT/logs"
mkdir -p "$LOGS"

stop_all() {
  pkill -f "node .*whatsapp_gateway" 2>/dev/null && echo "stopped gateway"
  pkill -f "python3 .*apps/server.py" 2>/dev/null && echo "stopped core"
  return 0
}

case "${1:-start}" in
  stop)
    stop_all
    exit 0
    ;;
  status)
    exec python3 "$ROOT/apps/status.py"
    ;;
esac

if [ ! -d "$GATEWAY/node_modules" ]; then
  echo "installing gateway dependencies..."
  (cd "$GATEWAY" && npm install --silent) || { echo "npm install failed"; exit 1; }
fi

stop_all >/dev/null 2>&1
sleep 1

echo "starting WhatsApp gateway..."
(cd "$GATEWAY" && node index.js > "$LOGS/gateway.log" 2>&1) &
sleep 6

echo "starting core..."
(cd "$ROOT" && python3 apps/server.py > "$LOGS/core.log" 2>&1) &
sleep 4

echo
python3 "$ROOT/apps/status.py"
echo "logs:  tail -f $LOGS/gateway.log   |   tail -f $LOGS/core.log"
echo "stop:  ./start.sh stop"
echo
echo "streaming logs (Ctrl+C leaves both running)..."
tail -f "$LOGS/core.log" "$LOGS/gateway.log"
