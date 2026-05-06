import logging
import random
import signal
import time

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


COLLECTOR_ENDPOINT = "http://localhost:4317"
SERVICE_NAME = "k8s-node"
NODE_NAMES = ["wayside-node-1", "wayside-node-2"]
INTERVAL_SECONDS = 10


stop_requested = False


def request_stop(signum, _frame) -> None:
    global stop_requested
    stop_requested = True
    logging.getLogger(SERVICE_NAME).info("Shutdown requested", extra={"signal": signum})


def configure_telemetry():
    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            #General attributes
            "sub_component.name": SERVICE_NAME,
            "component.type": "non-software-monitor",
            "fleet.name": "QNGR-OrbifloNG-PROD",
            "feature.name": "crosscutting-infrastructure",
            "feature.type": "crosscutting-component-infra",
            "component.name": "infrastructure-compute",
            "service.location": "wayside",
            #Lower level attributes
            "service.namespace": "sample-apps",
            "service.version": "1.0.0",
            "deployment.environment": "local",
            "component.layer": "infrastructure",
            "watchdog.target": "k8s-node",
            "watchdog.target.category": "node",
            "watchdog.check.type": "poll",
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=COLLECTOR_ENDPOINT, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=COLLECTOR_ENDPOINT, insecure=True),
        export_interval_millis=5000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=COLLECTOR_ENDPOINT, insecure=True))
    )

    LoggingInstrumentor().instrument(set_logging_format=True)

    logger = logging.getLogger(SERVICE_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(LoggingHandler(logger_provider=logger_provider))
    logger.propagate = False

    return (
        logger,
        trace.get_tracer(SERVICE_NAME),
        metrics.get_meter(SERVICE_NAME),
        tracer_provider,
        meter_provider,
        logger_provider,
    )


def main() -> None:
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    logger, tracer, meter, tracer_provider, meter_provider, logger_provider = configure_telemetry()

    # Watchdog metrics
    check_health = meter.create_gauge(
        name="watchdog.check.health",
        description="Health state from the last check (1=healthy, 0=unhealthy).",
        unit="1",
    )
    check_duration = meter.create_histogram(
        name="watchdog.check.duration",
        description="Duration of the watchdog health check.",
        unit="s",
    )
    consecutive_failures = meter.create_gauge(
        name="watchdog.consecutive_failures",
        description="Number of consecutive failed checks.",
        unit="{failure}",
    )
    last_check_ts = meter.create_gauge(
        name="watchdog.last_check.timestamp",
        description="Unix timestamp of the last check.",
        unit="s",
    )
    recovery_count = meter.create_counter(
        name="watchdog.recovery.count",
        description="Total recovery events observed.",
        unit="1",
    )
    component_health = meter.create_gauge(
        name="component.health.ratio",
        description="Overall component health ratio (1=healthy, 0.5=degraded, 0=unhealthy).",
        unit="1",
    )
    # Process metrics
    cpu_gauge = meter.create_gauge(
        name="process.cpu.usage",
        description="CPU usage of the process.",
        unit="%",
    )
    memory_gauge = meter.create_gauge(
        name="process.memory.usage",
        description="Memory usage of the process.",
        unit="%",
    )
    # Supplementary
    pods_gauge = meter.create_gauge(
        name="k8s.node.pods_running",
        description="Number of pods currently running on the node.",
        unit="{pod}",
    )
    restarts_counter = meter.create_counter(
        name="k8s.node.pod_restarts",
        description="Total simulated pod restarts observed on the node.",
        unit="1",
    )

    fail_streak = {n: 0 for n in NODE_NAMES}
    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            for node in NODE_NAMES:
                cpu = round(random.uniform(15.0, 65.0), 2)
                memory = round(random.uniform(30.0, 70.0), 2)
                pods = random.randint(8, 25)
                restarts = 0
                healthy = True
                dur = round(random.uniform(0.01, 0.15), 4)
                attrs = {"k8s.node.name": node}

                with tracer.start_as_current_span("k8s_node.sample", attributes=attrs):
                    check_duration.record(dur, attrs)
                    check_health.set(1 if healthy else 0, attrs)
                    component_health.set(1 if healthy else 0, attrs)
                    last_check_ts.set(time.time(), attrs)

                    if healthy:
                        if fail_streak[node] > 0:
                            recovery_count.add(1, attrs)
                        fail_streak[node] = 0
                    else:
                        fail_streak[node] += 1

                    consecutive_failures.set(fail_streak[node], attrs)
                    cpu_gauge.set(cpu, attrs)
                    memory_gauge.set(memory, attrs)
                    pods_gauge.set(pods, attrs)
                    if restarts:
                        restarts_counter.add(restarts, attrs)

                logger.info(
                    "Sampled K8s node metrics",
                    extra={
                        "node": node,
                        "cpu_percent": cpu,
                        "memory_percent": memory,
                        "pods_running": pods,
                        "restarts": restarts,
                        "healthy": healthy,
                    },
                )

            for _ in range(INTERVAL_SECONDS):
                if stop_requested:
                    break
                time.sleep(1)
    finally:
        logger.info("Flushing telemetry before shutdown")
        logger_provider.force_flush()
        meter_provider.force_flush()
        tracer_provider.force_flush()
        logger_provider.shutdown()
        meter_provider.shutdown()
        tracer_provider.shutdown()


if __name__ == "__main__":
    main()
