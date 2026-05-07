#!/usr/bin/env bash
# Runs all services (directories with app.py) inside Fleet-2 in the background.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
FLEET_DIR="$ROOT/metricsGenerators/Fleet-2"
VENV="$ROOT/metricsGenerators/RemoteWakeupAPI/.venv"
LOG_DIR="$ROOT/.logs/fleet2"
PID_DIR="$ROOT/.pids/fleet2"

if [[ ! -d "$VENV" ]]; then
  echo "Creating shared venv at $VENV"
  python3 -m venv "$VENV"
fi

PYTHON="$VENV/bin/python"

# Install all requirements.txt files found in Fleet-2
while IFS= read -r -d '' req; do
  "$VENV/bin/pip" install -q -r "$req"
done < <(find "$FLEET_DIR" -name requirements.txt -print0)

mkdir -p "$LOG_DIR" "$PID_DIR"

# Find and start all directories containing app.py (recursive)
found_any=false
while IFS= read -r -d '' app_py; do
  svc_dir="$(dirname "$app_py")"
  svc_name="$(basename "$svc_dir")"
  found_any=true

  pidfile="$PID_DIR/$svc_name.pid"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "[$svc_name] already running (pid $(cat "$pidfile"))"
    continue
  fi

  echo "[$svc_name] starting"
  ( cd "$svc_dir" && nohup "$PYTHON" app.py >"$LOG_DIR/$svc_name.log" 2>&1 & echo $! >"$pidfile" )
done < <(find "$FLEET_DIR" -name app.py -print0)

if ! $found_any; then
  echo "No services with app.py found in $FLEET_DIR"
fi

echo
echo "Running services:"
for pidfile in "$PID_DIR"/*.pid; do
  [[ -f "$pidfile" ]] || continue
  svc_name=$(basename "$pidfile" .pid)
  pid=$(cat "$pidfile" 2>/dev/null || echo "?")
  echo "  $svc_name -> pid $pid (log: .logs/fleet2/$svc_name.log)"
done
