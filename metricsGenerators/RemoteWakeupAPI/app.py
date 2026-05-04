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
SERVICE_NAME = "remote-wakeup-api"
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
            "service.namespace": "sample-apps",
            "service.version": "1.0.0",
            "service.instance.id": "remote-wakeup-api-001",
            "deployment.environment": "local",
            "platform.layer": "functional",
            "platform.feature": "remote-wakeup",
            "component.type": "microservice",
            "owner.team": "remote-wakeup",
            "runtime.kind": "service",
            "service.location": "wayside",
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

    # Latency
    request_duration = meter.create_histogram(
        name="http.server.request.duration",
        description="Duration of HTTP server requests.",
        unit="s",
    )
    # Traffic
    transaction_count = meter.create_counter(
        name="business.transaction.count",
        description="Total business transactions processed.",
        unit="1",
    )
    # Saturation
    active_requests = meter.create_gauge(
        name="http.server.active_requests",
        description="Number of active HTTP requests.",
        unit="{request}",
    )
    cpu_usage = meter.create_gauge(
        name="process.cpu.usage",
        description="CPU usage of the process.",
        unit="1",
    )
    memory_usage = meter.create_gauge(
        name="process.memory.usage",
        description="Memory usage of the process.",
        unit="By",
    )
    # Errors
    dependency_up = meter.create_gauge(
        name="service.dependency.up",
        description="Health state of service dependencies (1=up, 0=down).",
        unit="1",
    )

    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            device_id = f"charger-{random.randint(1000, 9999)}"
            duration_s = round(random.uniform(0.04, 0.25), 4)
            accepted = random.choice([True, True, True, False])
            wakeup_status = "accepted" if accepted else "rejected"
            attributes = {
                "device.id": device_id,
                "wakeup.status": wakeup_status,
            }

            concurrent = random.randint(1, 15)
            active_requests.set(concurrent)

            with tracer.start_as_current_span("remote_wakeup.dispatch", attributes=attributes) as span:
                span.add_event(
                    "remote_wakeup.requested",
                    {"device.id": device_id, "requested.at": int(time.time())},
                )
                time.sleep(duration_s)
                span.set_attribute("http.request.duration_s", duration_s)
                span.set_attribute("remote_wakeup.accepted", accepted)

            transaction_count.add(1, attributes)
            request_duration.record(duration_s, attributes)
            cpu_usage.set(round(random.uniform(0.05, 0.60), 4))
            memory_usage.set(random.randint(100_000_000, 500_000_000))
            dependency_up.set(1 if random.random() > 0.02 else 0, {"dependency.name": "rabbitmq"})

            logger.info(
                "Processed remote wakeup request",
                extra={
                    "device_id": device_id,
                    "wakeup_status": wakeup_status,
                    "duration_s": duration_s,
                    "iteration": iteration,
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
