# RemoteWakeupAPI

RemoteWakeupAPI is a sample Python service that simulates a remote charger wakeup workflow and publishes OpenTelemetry telemetry every 10 seconds.

The component is designed to run against the local observability stack in the repository root. It sends traces, metrics, and logs to the OpenTelemetry Collector on `localhost:4317`, and the collector routes each signal to the appropriate backend.

## Architecture

The repository contains a local monitoring stack with these services:

- OpenTelemetry Collector receives OTLP telemetry from the sample app.
- Prometheus scrapes metrics exposed by the collector.
- Loki stores logs exported by the collector.
- Tempo stores traces exported by the collector.
- Grafana queries Prometheus, Loki, and Tempo for exploration.

Telemetry flow:

```text
RemoteWakeupAPI
	-> OTLP/gRPC -> OpenTelemetry Collector
			-> Prometheus exporter -> Prometheus
			-> Loki exporter -> Loki
			-> OTLP exporter -> Tempo
Grafana
	-> queries Prometheus, Loki, and Tempo
```

## Component Behavior

Every loop iteration, the sample app:

- Creates a synthetic `device_id` such as `charger-1234`.
- Simulates a remote wakeup duration between roughly 40 ms and 250 ms.
- Randomly marks the wakeup as `accepted` or `rejected`.
- Creates a span for the dispatch action.
- Emits a metric update for request count and duration.
- Writes a structured log record with the same context.
- Waits 10 seconds before generating the next event.

This makes the component useful for validating that all three telemetry signals are visible end to end in Grafana.

## Metrics Sent By RemoteWakeupAPI

The service currently emits these OpenTelemetry metrics:

### `remote_wakeup_requests_total`

Type: Counter

Purpose: Counts how many synthetic remote wakeup requests were processed.

Typical labels:

- `device_id`
- `wakeup_status`
- `loop_iteration`
- `service_name`
- `service_namespace`
- `deployment_environment`

Example Prometheus query:

```promql
remote_wakeup_requests_total{service_name="remote-wakeup-api"}
```

### `remote_wakeup_duration_ms`

Type: Histogram

Purpose: Records the simulated duration of each remote wakeup request in milliseconds.

Typical labels:

- `device_id`
- `wakeup_status`
- `loop_iteration`
- `service_name`
- `service_namespace`
- `deployment_environment`

Example Prometheus queries:

```promql
remote_wakeup_duration_ms_count{service_name="remote-wakeup-api"}
```

```promql
remote_wakeup_duration_ms_sum{service_name="remote-wakeup-api"}
```

## Traces And Logs

The component also emits:

- A span named `remote_wakeup.dispatch`.
- A span event named `remote_wakeup.requested`.
- Structured logs such as `Processed remote wakeup request`.

Important label and attribute mapping details:

- In Loki, the OpenTelemetry resource attribute `service.name` is exposed as the label `service_name`.
- In Prometheus, `service.name` also appears as `service_name` because Prometheus label names cannot contain dots.

## Run

```bash
cd /home/carlos/lab/monitoring-structure/RemoteWakeupAPI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Explore In Grafana

Useful starting queries:

### Prometheus

```promql
remote_wakeup_requests_total{service_name="remote-wakeup-api"}
```

```promql
remote_wakeup_duration_ms_count{service_name="remote-wakeup-api"}
```

### Loki

```logql
{service_name="sample-apps/remote-wakeup-api"}
```

### Tempo

Search for traces with:

- `service.name = remote-wakeup-api`

## Files

- `app.py` contains the sample telemetry loop.
- `requirements.txt` defines the OpenTelemetry Python dependencies.
- `../otel-collector-config.yaml` defines how the collector routes the three telemetry signals.