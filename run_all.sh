#!/usr/bin/env bash
# Runs all sample services in the background using the shared RemoteWakeupAPI venv.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/metricsGenerators/RemoteWakeupAPI/.venv"
LOG_DIR="$ROOT/.logs"
PID_DIR="$ROOT/.pids"

if [[ ! -d "$VENV" ]]; then
  echo "Creating shared venv at $VENV"
  python3 -m venv "$VENV"
fi

PYTHON="$VENV/bin/python"
"$VENV/bin/pip" install -q -r "$ROOT/metricsGenerators/Fleet/Remote Wakeup (Feature)/RemoteWakeupAPI/requirements.txt"

mkdir -p "$LOG_DIR" "$PID_DIR"

# Map: service key -> path relative to metricsGenerators/Fleet/
declare -A SERVICE_PATHS=(
  ["RemoteWakeupAPI"]="Remote Wakeup (Feature)/RemoteWakeupAPI"
  ["RemoteWakeupService"]="Remote Wakeup (Feature)/RemoteWakeupService"
  ["K8sNode"]="Crosscutting Component (Infrastructure)/Infrastructure Compute/K8sNode"
  ["T2GGateway"]="Crosscutting Component (Infrastructure)/Infrastructure Compute/T2GGateway"
  ["RabbitMQ"]="Crosscutting Component (Infrastructure)/Infrastructure Compute/RabbitMQ"
  ["MQTTBroker"]="Crosscutting Component (Infrastructure)/Infrastructure Compute/MQTTBroker"
  ["VPNTerminatorGround"]="Crosscutting Component (Infrastructure)/Infrastrucutre Network/VPNTerminatorGround"
  ["VPNMonitor"]="Crosscutting Component (Infrastructure)/Infrastrucutre Network/VPNMonitor"
)

SERVICES=(RemoteWakeupAPI RemoteWakeupService K8sNode T2GGateway RabbitMQ MQTTBroker VPNTerminatorGround VPNMonitor)

for svc in "${SERVICES[@]}"; do
  pidfile="$PID_DIR/$svc.pid"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "[$svc] already running (pid $(cat "$pidfile"))"
    continue
  fi
  svc_dir="$ROOT/metricsGenerators/Fleet/${SERVICE_PATHS[$svc]}"
  echo "[$svc] starting"
  ( cd "$svc_dir" && nohup "$PYTHON" app.py >"$LOG_DIR/$svc.log" 2>&1 & echo $! >"$pidfile" )
done

echo
echo "Running services:"
for svc in "${SERVICES[@]}"; do
  pid=$(cat "$PID_DIR/$svc.pid" 2>/dev/null || echo "?")
  echo "  $svc -> pid $pid (log: .logs/$svc.log)"
done
