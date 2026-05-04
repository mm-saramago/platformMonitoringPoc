#!/usr/bin/env bash
# Runs all sample services in the background using the shared RemoteWakeupAPI venv.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/RemoteWakeupAPI/.venv"
LOG_DIR="$ROOT/.logs"
PID_DIR="$ROOT/.pids"

if [[ ! -d "$VENV" ]]; then
  echo "Creating shared venv at $VENV"
  python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q -r "$ROOT/RemoteWakeupAPI/requirements.txt"

mkdir -p "$LOG_DIR" "$PID_DIR"

SERVICES=(
  "RemoteWakeupAPI"
  "RemoteWakeupService"
  "K8sNode"
  "T2GGateway"
  "RabbitMQ"
  "MQTTBroker"
  "VPNTerminatorGround"
  "VPNMonitor"
)

for svc in "${SERVICES[@]}"; do
  pidfile="$PID_DIR/$svc.pid"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "[$svc] already running (pid $(cat "$pidfile"))"
    continue
  fi
  echo "[$svc] starting"
  ( cd "$ROOT/$svc" && nohup python app.py >"$LOG_DIR/$svc.log" 2>&1 & echo $! >"$pidfile" )
done

echo
echo "Running services:"
for svc in "${SERVICES[@]}"; do
  pid=$(cat "$PID_DIR/$svc.pid" 2>/dev/null || echo "?")
  echo "  $svc -> pid $pid (log: .logs/$svc.log)"
done
