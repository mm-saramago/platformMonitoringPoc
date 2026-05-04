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


def configure_telemetry():
    resource = Resource.create({
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

    request_duration = meter.create_histogram(name="http.server.request.duration", description="Duration of HTTP server requests.", unit="s")
    transaction_count = meter.create_counter(name="business.transaction.count", description="Total business transactions processed.", unit="1")
    active_requests = meter.create_gauge(name="http.server.active_requests", description="Number of active HTTP requests.", unit="{request}")
    cpu_usage = meter.create_gauge(name="process.cpu.usage", description="CPU usage of the process.", unit="1")
    memory_usage = meter.create_gauge(name="process.memory.usage", description="Memory usage of the process.", unit="By")
    dependency_up = meter.create_gauge(name="service.dependency.up", description="Health state of service dependencies (1=up, 0=down).", unit="1")

    queued = 10
    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            queued = min(queued + random.randint(1, 5), 100)
            dur = round(random.uniform(3.0, 15.0), 3)
            device_id = f"charger-{random.randint(1000, 9999)}"
            attrs = {"device.id": device_id, "wakeup.status": "timeout"}

            with tracer.start_as_current_span("remote_wakeup.dispatch", attributes=attrs) as span:
                span.set_attribute("error", True)
                span.set_attribute("otel.status_code", "ERROR")

            transaction_count.add(1, attrs)
            request_duration.record(dur, attrs)
            active_requests.set(queued)
            cpu_usage.set(round(random.uniform(0.70, 0.95), 3))
            memory_usage.set(random.randint(600_000_000, 900_000_000))
            dependency_up.set(0, {"dependency.name": "rabbitmq"})

            logger.error(
                "dependency rabbitmq DOWN - wakeup request for %s queued, timeout after %.1fs",
                device_id, dur,
                extra={"device_id": device_id, "duration_s": dur, "queued_requests": queued},
            )
            logger.warning(
                "request backlog growing: %d requests waiting",
                queued,
                extra={"active_requests": queued},
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
