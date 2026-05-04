#!/usr/bin/env bash
# ---------------------------------------------------------------
# Cascading-failure demo.
#
# 1. Stops any currently running healthy generators (stop_all.sh)
# 2. Launches error-scenario generators that simulate:
#      ROOT CAUSE:  K8s-node-1 disk-full  -->  node NotReady
#      CASCADE:     RabbitMQ / MQTT queues back up
#                   T2G Gateway loses dependency, starts rate-limiting
#                   VPN tunnels degrade (ground + onboard)
#                   Remote-Wakeup API times out, requests pile up
#                   Remote-Wakeup Service loses all trains
#
# Usage:  ./run_error.sh          -- start error scenario
#         ./stop_error.sh         -- stop and return to normal
#         ./run_all.sh            -- restart healthy generators
# ---------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/metricsGenerators/RemoteWakeupAPI/.venv"
LOG_DIR="$ROOT/.logs"
PID_DIR="$ROOT/.pids"

echo "=== Stopping healthy generators first ==="
bash "$ROOT/stop_all.sh" 2>/dev/null || true

echo "=== Restarting OTel Collector to flush stale metrics ==="
(cd "$ROOT" && docker compose restart otel-collector 2>/dev/null) || true
sleep 3

if [[ ! -d "$VENV" ]]; then
  echo "Creating shared venv at $VENV"
  python3 -m venv "$VENV"
fi

PYTHON="$VENV/bin/python"
"$VENV/bin/pip" install -q -r "$ROOT/metricsGenerators/RemoteWakeupAPI/requirements.txt"

mkdir -p "$LOG_DIR" "$PID_DIR"

# Map: pid-name -> script-path (relative to error/)
declare -A ERROR_GENERATORS=(
  [K8sNode]="k8s_node_error.py"
  [RabbitMQ]="rabbitmq_error.py"
  [MQTTBroker]="mqtt_broker_error.py"
  [T2GGateway]="t2g_gateway_error.py"
  [VPNTerminatorGround]="vpn_terminator_ground_error.py"
  [VPNMonitor]="vpn_monitor_error.py"
  [RemoteWakeupAPI]="remote_wakeup_api_error.py"
  [RemoteWakeupService]="remote_wakeup_service_error.py"
)

echo
echo "=== Launching error scenario generators ==="
for svc in "${!ERROR_GENERATORS[@]}"; do
  script="${ERROR_GENERATORS[$svc]}"
  pidfile="$PID_DIR/$svc.pid"

  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "[$svc] already running (pid $(cat "$pidfile"))"
    continue
  fi

  echo "[$svc] starting error generator -> $script"
  (
    cd "$ROOT/metricsGenerators/error"
    nohup "$PYTHON" "$script" >"$LOG_DIR/${svc}_error.log" 2>&1 &
    echo $! >"$pidfile"
  )
done

echo
echo "=== Error scenario active ==="
echo "Root cause: wayside-node-1 disk full -> cascading infrastructure failure"
echo
echo "Running error generators:"
for svc in "${!ERROR_GENERATORS[@]}"; do
  pid=$(cat "$PID_DIR/$svc.pid" 2>/dev/null || echo "?")
  echo "  $svc -> pid $pid (log: .logs/${svc}_error.log)"
done
echo
echo "Open Grafana at http://localhost:3000"
echo "  1. Fleet Dashboard     -> all features show DEGRADED"
echo "  2. Crosscutting Infra  -> RabbitMQ, MQTT, VPN, Gateway all red"
echo "  3. K8s Node Dashboard  -> wayside-node-1 CRITICAL (root cause)"
echo
echo "To stop:  ./stop_error.sh"
echo "To recover:  ./stop_error.sh && ./run_all.sh"
