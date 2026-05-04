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
SERVICE_NAME = "t2g-gateway"
INTERVAL_SECONDS = 10

stop_requested = False


def request_stop(signum, _frame) -> None:
    global stop_requested
    stop_requested = True


def configure_telemetry():
    resource = Resource.create({
            "service.name": SERVICE_NAME,
            "service.namespace": "sample-apps",
            "service.version": "1.0.0",
            "deployment.environment": "local",
            "component.layer": "crosscutting",
            "component.type": "crosscutting-service",
            "component.subtype": "api-gateway",
            "platform.feature": "infrastructure",
            "service.location": "wayside",
        })

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

    routing_duration = meter.create_histogram(name="gateway.request.routing.duration", description="Latency of routing a message through the gateway.", unit="s")
    connections_active = meter.create_gauge(name="gateway.connections.active", description="Number of train connections currently bridged.", unit="{connection}")
    rate_limit_exceeded = meter.create_counter(name="gateway.rate_limit.exceeded", description="Requests rejected by rate limiting.", unit="1")
    http_duration = meter.create_histogram(name="http.server.request.duration", description="Duration of HTTP server requests.", unit="s")
    active_requests = meter.create_gauge(name="http.server.active_requests", description="Number of active HTTP requests.", unit="{request}")
    cpu_usage = meter.create_gauge(name="process.cpu.usage", description="CPU usage of the process.", unit="1")
    memory_usage = meter.create_gauge(name="process.memory.usage", description="Memory usage of the process.", unit="By")
    dependency_up = meter.create_gauge(name="service.dependency.up", description="Health state of service dependencies (1=up, 0=down).", unit="1")

    conn_count = 45
    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            conn_count = max(0, conn_count - random.randint(1, 5))
            train_id = f"train-{random.randint(1, 50):03d}"
            dur = round(random.uniform(2.0, 15.0), 3)
            attrs = {"train.id": train_id, "route.direction": "uplink", "route.status": "failed"}

            with tracer.start_as_current_span("t2g_gateway.route", attributes=attrs):
                routing_duration.record(dur, attrs)
                http_duration.record(dur + 0.5, attrs)

            connections_active.set(conn_count)
            active_requests.set(random.randint(30, 80))
            rate_limit_exceeded.add(random.randint(5, 20), {"train.id": train_id})
            cpu_usage.set(round(random.uniform(0.7, 0.95), 3))
            memory_usage.set(random.randint(700_000_000, 950_000_000))
            dependency_up.set(0, {"dependency.name": "rabbitmq"})

            logger.error(
                "dependency rabbitmq unreachable - message routing failing",
                extra={"train_id": train_id, "active_connections": conn_count, "duration_s": dur},
            )
            logger.warning(
                "rate limiting triggered, %d requests rejected",
                random.randint(5, 20),
                extra={"connections_dropping": True},
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
