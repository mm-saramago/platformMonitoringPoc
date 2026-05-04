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

## Metric Generators

| Service                | Layer          | Description                              |
|------------------------|----------------|------------------------------------------|
| RemoteWakeupAPI        | —              | Simulates remote wakeup request dispatch |
| RemoteWakeupService    | functional     | Simulates on-vehicle wakeup execution    |
| K8sNode                | infrastructure | Simulates K8s node CPU/memory/pod stats  |
| T2GGateway             | crosscutting   | Simulates train-to-ground message routing|
| RabbitMQ               | infrastructure | Simulates AMQP queue depth and throughput|
| MQTTBroker             | infrastructure | Simulates MQTT client/message activity   |
| VPNTerminatorGround    | infrastructure | Simulates ground-side VPN termination    |
| VPNMonitor             | infrastructure | Simulates on-board VPN tunnel probing    |

## Prerequisites

- Docker & Docker Compose
- Python 3.10+

## Quick Start

**1. Start the observability stack:**

```bash
docker compose up -d
```

**2. Start the metric generators:**

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
