#!/usr/bin/env bash
# Stops error-scenario generators launched by run_error.sh.
# Reuses the same .pids directory as the normal generators.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$ROOT/.pids"

if [[ ! -d "$PID_DIR" ]]; then
  echo "No pid dir; nothing to stop."
  exit 0
fi

for pidfile in "$PID_DIR"/*.pid; do
  [[ -e "$pidfile" ]] || continue
  svc=$(basename "$pidfile" .pid)
  pid=$(cat "$pidfile")
  if kill -0 "$pid" 2>/dev/null; then
    echo "[$svc] stopping pid $pid"
    kill "$pid" || true
  else
    echo "[$svc] not running"
  fi
  rm -f "$pidfile"
done

echo
echo "Error scenario stopped."
echo "Restarting OTel Collector to flush error metrics..."
(cd "$ROOT" && docker compose restart otel-collector 2>/dev/null) || true
echo "To restore healthy generators: ./run_all.sh"
