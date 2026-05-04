# Metrics Alignment with Monitoring Specification

This document maps each metric generator to its **component type** (per `doc.md` Chapter 6) and lists the **required metrics** (per Chapter 8), comparing them against what is currently implemented.

Legend: [YES] Implemented | [NO] Missing

---

## RemoteWakeupAPI -- Microservice (Section 8.2)

| Required Metric | OTel Name | Type | Unit | Prometheus Name | Status |
|-----------------|-----------|------|------|-----------------|--------|
| Request duration | `http.server.request.duration` | Histogram | s | `http_server_request_duration_seconds_*` | [YES] |
| Active requests | `http.server.active_requests` | Gauge | {request} | `http_server_active_requests` | [YES] |
| CPU usage | `process.cpu.usage` | Gauge | 1 | `process_cpu_usage_ratio` | [YES] |
| Memory usage | `process.memory.usage` | Gauge | By | `process_memory_usage_bytes` | [YES] |
| Dependency health | `service.dependency.up` | Gauge | 1 | `service_dependency_up_ratio` | [YES] |
| Transaction count | `business.transaction.count` | Counter | 1 | `business_transaction_count_total` | [YES] |

**Resource attributes:** `service.version`, `service.instance.id`, `platform.layer`, `platform.feature`, `component.type=microservice`, `owner.team`, `runtime.kind=service`, `service.location=wayside`

---

## RemoteWakeupService -- Train-Side Onboard Software (Section 8.5)

| Required Metric | OTel Name | Type | Unit | Prometheus Name | Status |
|-----------------|-----------|------|------|-----------------|--------|
| Heartbeat timestamp | `vehicle.heartbeat.timestamp` | Gauge | s | `vehicle_heartbeat_timestamp_seconds` | [YES] |
| Heartbeat lag | `vehicle.heartbeat.lag` | Gauge | s | `vehicle_heartbeat_lag_seconds` | [YES] |
| Connectivity state | `vehicle.connectivity.state` | Gauge | 1 | `vehicle_connectivity_state_ratio` | [YES] |
| Message backlog | `vehicle.message.backlog` | Gauge | {message} | `vehicle_message_backlog` | [YES] |
| Message sync count | `vehicle.message.sync.count` | Counter | {message} | `vehicle_message_sync_count_total` | [YES] |
| CPU usage | `vehicle.cpu.usage` | Gauge | % | `vehicle_cpu_usage_percent` | [YES] |
| Memory usage | `vehicle.memory.usage` | Gauge | % | `vehicle_memory_usage_percent` | [YES] |
| Storage usage | `vehicle.storage.usage` | Gauge | % | `vehicle_storage_usage_percent` | [YES] |
| Error count | `vehicle.error.count` | Counter | 1 | `vehicle_error_count_total` | [YES] |
| Update status | `vehicle.update.status` | Gauge | 1 | `vehicle_update_status_ratio` | [YES] |

**Resource attributes:** `component.type=onboard`, `runtime.kind=agent`, `service.location=onboard`, `vehicle.fleet`

---

## K8sNode -- Non-Software Monitor / Watchdog (Section 8.6)

| Required Metric | OTel Name | Type | Unit | Prometheus Name | Status |
|-----------------|-----------|------|------|-----------------|--------|
| Health check | `watchdog.check.health` | Gauge | 1 | `watchdog_check_health_ratio` | [YES] |
| Check duration | `watchdog.check.duration` | Histogram | s | `watchdog_check_duration_seconds_*` | [YES] |
| Consecutive failures | `watchdog.consecutive_failures` | Gauge | {failure} | `watchdog_consecutive_failures` | [YES] |
| Last check timestamp | `watchdog.last_check.timestamp` | Gauge | s | `watchdog_last_check_timestamp_seconds` | [YES] |
| Recovery count | `watchdog.recovery.count` | Counter | 1 | `watchdog_recovery_count_total` | [YES] |
| CPU usage | `process.cpu.usage` | Gauge | % | `process_cpu_usage_percent` | [YES] |
| Memory usage | `process.memory.usage` | Gauge | % | `process_memory_usage_percent` | [YES] |

Supplementary: `k8s.node.pods_running`, `k8s.node.pod_restarts`

**Resource attributes:** `component.type=watchdog`, `watchdog.target=k8s-node`, `watchdog.target.category=node`, `watchdog.check.type=poll`

---

## T2GGateway -- Crosscutting Service / API Gateway (Section 8.4.1)

| Required Metric | OTel Name | Type | Unit | Prometheus Name | Status |
|-----------------|-----------|------|------|-----------------|--------|
| Routing duration | `gateway.request.routing.duration` | Histogram | s | `gateway_request_routing_duration_seconds_*` | [YES] |
| Active connections | `gateway.connections.active` | Gauge | {connection} | `gateway_connections_active` | [YES] |
| Rate limit exceeded | `gateway.rate_limit.exceeded` | Counter | 1 | `gateway_rate_limit_exceeded_total` | [YES] |
| HTTP request duration | `http.server.request.duration` | Histogram | s | `http_server_request_duration_seconds_*` | [YES] |
| HTTP active requests | `http.server.active_requests` | Gauge | {request} | `http_server_active_requests` | [YES] |
| CPU usage | `process.cpu.usage` | Gauge | 1 | `process_cpu_usage_ratio` | [YES] |
| Memory usage | `process.memory.usage` | Gauge | By | `process_memory_usage_bytes` | [YES] |
| Dependency health | `service.dependency.up` | Gauge | 1 | `service_dependency_up_ratio` | [YES] |

**Resource attributes:** `component.type=crosscutting-service`, `component.subtype=api-gateway`, `platform.feature=infrastructure`

---

## RabbitMQ -- Crosscutting Service / Messaging (Section 8.4.3)

| Required Metric | OTel Name | Type | Unit | Prometheus Name | Status |
|-----------------|-----------|------|------|-----------------|--------|
| Publish messages | `messaging.publish.messages` | Counter | {message} | `messaging_publish_messages_total` | [YES] |
| Process messages | `messaging.process.messages` | Counter | {message} | `messaging_process_messages_total` | [YES] |
| Queue depth | `messaging.queue.depth` | Gauge | {message} | `messaging_queue_depth` | [YES] |
| Publish duration | `messaging.publish.duration` | Histogram | s | `messaging_publish_duration_seconds_*` | [YES] |
| Process duration | `messaging.process.duration` | Histogram | s | `messaging_process_duration_seconds_*` | [YES] |
| Consumer lag | `messaging.consumer.lag` | Gauge | {message} | `messaging_consumer_lag` | [YES] |
| Consumer lag (time) | `messaging.consumer.lag_seconds` | Gauge | s | `messaging_consumer_lag_seconds` | [YES] |

**Resource attributes:** `component.type=crosscutting-service`, `component.subtype=message-broker`, `messaging.system=rabbitmq`

---

## MQTTBroker -- Crosscutting Service / Messaging (Section 8.4.3)

| Required Metric | OTel Name | Type | Unit | Prometheus Name | Status |
|-----------------|-----------|------|------|-----------------|--------|
| Publish messages | `messaging.publish.messages` | Counter | {message} | `messaging_publish_messages_total` | [YES] |
| Process messages | `messaging.process.messages` | Counter | {message} | `messaging_process_messages_total` | [YES] |
| Queue depth | `messaging.queue.depth` | Gauge | {message} | `messaging_queue_depth` | [YES] |
| Publish duration | `messaging.publish.duration` | Histogram | s | `messaging_publish_duration_seconds_*` | [YES] |
| Process duration | `messaging.process.duration` | Histogram | s | `messaging_process_duration_seconds_*` | [YES] |
| Consumer lag | `messaging.consumer.lag` | Gauge | {message} | `messaging_consumer_lag` | [YES] |

**Resource attributes:** `component.type=crosscutting-service`, `component.subtype=message-broker`, `messaging.system=mqtt`

---

## VPNTerminatorGround -- Non-Software Monitor / Watchdog (Section 8.6)

| Required Metric | OTel Name | Type | Unit | Prometheus Name | Status |
|-----------------|-----------|------|------|-----------------|--------|
| Health check | `watchdog.check.health` | Gauge | 1 | `watchdog_check_health_ratio` | [YES] |
| Check duration | `watchdog.check.duration` | Histogram | s | `watchdog_check_duration_seconds_*` | [YES] |
| Consecutive failures | `watchdog.consecutive_failures` | Gauge | {failure} | `watchdog_consecutive_failures` | [YES] |
| Last check timestamp | `watchdog.last_check.timestamp` | Gauge | s | `watchdog_last_check_timestamp_seconds` | [YES] |
| Recovery count | `watchdog.recovery.count` | Counter | 1 | `watchdog_recovery_count_total` | [YES] |
| Failover triggered | `watchdog.failover.triggered` | Counter | 1 | `watchdog_failover_triggered_total` | [YES] |
| Packet loss | `watchdog.packet.loss` | Gauge | % | `watchdog_packet_loss_percent` | [YES] |
| TCP connection duration | `watchdog.tcp.connection.duration` | Histogram | s | `watchdog_tcp_connection_duration_seconds_*` | [YES] |

Supplementary: `vpn.terminator.active_tunnels`, `vpn.terminator.throughput_mbps`

**Resource attributes:** `component.type=watchdog`, `watchdog.target=vpn-tunnel`, `watchdog.target.category=network`, `watchdog.check.type=probe`, `service.location=wayside`

---

## VPNMonitor -- Non-Software Monitor / Watchdog, train-side (Section 8.6)

| Required Metric | OTel Name | Type | Unit | Prometheus Name | Status |
|-----------------|-----------|------|------|-----------------|--------|
| Health check | `watchdog.check.health` | Gauge | 1 | `watchdog_check_health_ratio` | [YES] |
| Check duration | `watchdog.check.duration` | Histogram | s | `watchdog_check_duration_seconds_*` | [YES] |
| Consecutive failures | `watchdog.consecutive_failures` | Gauge | {failure} | `watchdog_consecutive_failures` | [YES] |
| Last check timestamp | `watchdog.last_check.timestamp` | Gauge | s | `watchdog_last_check_timestamp_seconds` | [YES] |
| Recovery count | `watchdog.recovery.count` | Counter | 1 | `watchdog_recovery_count_total` | [YES] |
| Packet loss | `watchdog.packet.loss` | Gauge | % | `watchdog_packet_loss_percent` | [YES] |

**Resource attributes:** `component.type=watchdog`, `watchdog.target=vpn-tunnel`, `watchdog.check.type=probe`, `service.location=onboard`

---

## Summary

| Service             | Component Type              | Required | Implemented | Compliance |
|---------------------|-----------------------------|----------|-------------|------------|
| RemoteWakeupAPI     | Microservice                | 6        | 6           | Full       |
| RemoteWakeupService | Train-Side Onboard          | 10       | 10          | Full       |
| K8sNode             | Watchdog                    | 7        | 7           | Full       |
| T2GGateway          | Crosscutting / API Gateway  | 8        | 8           | Full       |
| RabbitMQ            | Crosscutting / Messaging    | 7        | 7           | Full       |
| MQTTBroker          | Crosscutting / Messaging    | 6        | 6           | Full       |
| VPNTerminatorGround | Watchdog                    | 8        | 8           | Full       |
| VPNMonitor          | Watchdog (train-side)       | 6        | 6           | Full       |

All generators now have **resource attributes aligned** with the tagging strategy (Chapter 7).
