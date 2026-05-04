# Platform Monitoring POC

Proof-of-concept for a three-pillar observability stack (metrics, logs, traces) using OpenTelemetry, Prometheus, Grafana, Loki, and Tempo.

## Architecture

```
┌─────────────────────┐
│  Metric Generators   │  8 Python services producing synthetic telemetry
│  (metricsGenerators) │
└────────┬────────────┘
         │ OTLP gRPC (:4317)
         ▼
┌─────────────────────┐
│   OTel Collector     │  Central aggregation & routing
└──┬───────┬────────┬─┘
   │       │        │
   ▼       ▼        ▼
Loki    Prometheus  Tempo
:3100    :9090      :3200
   │       │        │
   └───────┼────────┘
           ▼
       Grafana (:3000)
```

## Dashboard Hierarchy

```
Fleet Dashboard
├── Remote Wakeup (Feature)  ──>  Feature Dashboard
│   ├── Remote Wakeup API       ──>  Component Dashboard
│   └── Remote Wakeup Service   ──>  Component Dashboard
└── Crosscutting Infrastructure  ──>  Crosscutting Infra Dashboard
    ├── K8s Node                 ──>  Infra Dashboard
    ├── T2G Gateway              ──>  Infra Dashboard
    ├── RabbitMQ                 ──>  Infra Dashboard
    ├── MQTT Broker              ──>  Infra Dashboard
    ├── VPN Terminator Ground    ──>  Infra Dashboard
    └── VPN Monitor              ──>  Infra Dashboard
```

Each panel is a clickable health indicator that drills down to the next level.

## Health Model

Every component computes a health value from 0 to 1:

| Value | State | Color | Meaning |
|-------|-------|-------|---------|
| 1 | HEALTHY | Green | All checks pass |
| 0.5 | DEGRADED | Orange | Partial failure (e.g. 1 of 2 nodes down) |
| 0 | UNHEALTHY | Red | Component down or critical threshold breached |

Health rolls up through the hierarchy: fleet health = average of all child component healths.

See `metrics.md` for the full threshold and rollup specification.

## Metric Generators

| Service             | Component Type               | Health Signal                    |
|---------------------|------------------------------|----------------------------------|
| RemoteWakeupAPI     | Microservice                 | `service.dependency.up`          |
| RemoteWakeupService | Train-Side Onboard           | `vehicle.connectivity.state`     |
| K8sNode             | Watchdog                     | `watchdog.check.health`          |
| T2GGateway          | Crosscutting / API Gateway   | `service.dependency.up`          |
| RabbitMQ            | Crosscutting / Messaging     | `messaging.queue.depth`          |
| MQTTBroker          | Crosscutting / Messaging     | `messaging.queue.depth`          |
| VPNTerminatorGround | Watchdog                     | `watchdog.check.health`          |
| VPNMonitor          | Watchdog (train-side)        | `watchdog.check.health`          |

## Prerequisites

- Docker & Docker Compose
- Python 3.10+

## Quick Start

**1. Start the observability stack:**

```bash
docker compose up -d
```

**2. Start the metric generators (healthy scenario):**

```bash
./run_all.sh
```

**3. Open Grafana:**

http://localhost:3000 (admin / admin)

**4. Stop the generators:**

```bash
./stop_all.sh
```

**5. Tear down the stack:**

```bash
docker compose down
```

## Error Scenario (Cascading Failure Demo)

Simulates a disk-full event on wayside-node-1 that cascades through the entire infrastructure.

**Start the error scenario:**

```bash
./run_error.sh
```

This stops healthy generators, restarts the OTel Collector, and launches error-mode generators that produce:

- **K8s Node** (root cause): CPU 95-99%, memory 96-100%, health=0, disk full logs
- **RabbitMQ / MQTT**: Queue depth 3,000-15,000, consumers stalled
- **T2G Gateway**: Dependency down, rate limiting, connections dropping
- **VPN Terminator / Monitor**: All tunnels down, packet loss 15-60%
- **Remote Wakeup API**: Dependency timeout, request backlog growing
- **Remote Wakeup Service**: All trains offline, heartbeat lag 300s+

**Drill-down workflow in Grafana:**

1. **Fleet Dashboard** -- Feature and Infrastructure both show DEGRADED/UNHEALTHY
2. **Crosscutting Infra** -- Click to see which infra components are red
3. **K8s Node Dashboard** -- wayside-node-1 shows root cause: disk full, CPU/memory critical

**Stop the error scenario and recover:**

```bash
./stop_error.sh
./run_all.sh
```

## Changing Thresholds

Health thresholds are defined in two places:

### 1. Dashboard Panel Thresholds (visual indicators)

Edit the JSON files in `grafana/provisioning/dashboards/json/`. Each panel has a `thresholds` block:

```json
"thresholds": {
  "mode": "absolute",
  "steps": [
    { "color": "green", "value": null },
    { "color": "yellow", "value": 60 },
    { "color": "red", "value": 85 }
  ]
}
```

- `null` = base (everything below the next step)
- Steps are evaluated in order; the last matching step wins

**Current panel thresholds:**

| Metric | Green | Yellow | Red | Dashboard |
|--------|-------|--------|-----|-----------|
| CPU usage | < 85% | 85-90% | > 90% | component, infra-k8s-node |
| Memory usage | < 90% | 90-95% | > 95% | component, infra-k8s-node |
| Queue depth | < 500 | 500-2,000 | > 2,000 | infra-rabbitmq, infra-mqtt |
| Packet loss | < 1% | 1-5% | > 5% | infra-vpn-* |
| Consecutive failures | < 2 | 2-5 | > 5 | infra-k8s-node, infra-vpn-term |

After editing, restart Grafana to reload provisioned dashboards:

```bash
docker compose restart grafana
```

### 2. Health Rollup Queries (stat panels on Fleet / Feature / Crosscutting dashboards)

These use PromQL to compute a 0-1 health score. Edit the `expr` field in the stat panel's `targets`:

**Watchdog components** (binary health per instance, averaged):
```promql
avg(watchdog_check_health_ratio{service_name="k8s-node"}) or on() vector(0)
```

**Dependency-based** (worst-of across deps):
```promql
min(service_dependency_up_ratio{service_name="t2g-gateway"}) or on() vector(0)
```

**Queue-depth step function** (configurable breakpoints at 500 and 2000):
```promql
((max(messaging_queue_depth{service_name="rabbitmq"}) < bool 2000)
 + (max(messaging_queue_depth{service_name="rabbitmq"}) < bool 500)) / 2
or on() vector(1)
```

To change the queue depth breakpoints, replace `500` and `2000` with your desired values in both the component dashboard (`crosscutting-infra.json`) and the fleet rollup (`fleet.json`).

### 3. Value Mappings (text labels)

Each stat panel maps numeric ranges to text:

```json
"mappings": [
  { "type": "range", "options": { "from": 0, "to": 0.49, "result": { "text": "UNHEALTHY", "color": "red" }}},
  { "type": "range", "options": { "from": 0.5, "to": 0.99, "result": { "text": "DEGRADED", "color": "orange" }}},
  { "type": "range", "options": { "from": 1, "to": 1, "result": { "text": "HEALTHY", "color": "green" }}}
]
```

## Ports

| Service         | Port  |
|-----------------|-------|
| Grafana         | 3000  |
| Loki            | 3100  |
| Tempo           | 3200  |
| OTel Collector  | 4317 (gRPC), 4318 (HTTP), 9464 (Prometheus) |
| Prometheus      | 9090  |

## Dashboards

Pre-provisioned Grafana dashboards are in `grafana/provisioning/dashboards/json/`.

## Further Reading

- `metrics.md` -- Metric compliance matrix, threshold tables, and health rollup formulas
