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


def configure_telemetry() -> tuple[
    logging.Logger,
    trace.Tracer,
    metrics.Meter,
    TracerProvider,
    MeterProvider,
    LoggerProvider,
]:
    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.namespace": "sample-apps",
            "deployment.environment": "local",
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

    request_counter = meter.create_counter(
        name="remote_wakeup_requests_total",
        description="Total number of remote wakeup requests sent by the sample app.",
        unit="1",
    )
    latency_histogram = meter.create_histogram(
        name="remote_wakeup_duration_ms",
        description="Observed duration of the remote wakeup loop iteration.",
        unit="ms",
    )

    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            device_id = f"charger-{random.randint(1000, 9999)}"
            simulated_duration_ms = round(random.uniform(40.0, 250.0), 2)
            accepted = random.choice([True, True, True, False])
            wakeup_status = "accepted" if accepted else "rejected"
            attributes = {
                "device.id": device_id,
                "wakeup.status": wakeup_status,
                "loop.iteration": iteration,
            }

            with tracer.start_as_current_span("remote_wakeup.dispatch", attributes=attributes) as span:
                span.add_event(
                    "remote_wakeup.requested",
                    {
                        "device.id": device_id,
                        "requested.at": int(time.time()),
                    },
                )
                time.sleep(simulated_duration_ms / 1000)
                span.set_attribute("remote_wakeup.duration_ms", simulated_duration_ms)
                span.set_attribute("remote_wakeup.accepted", accepted)

            request_counter.add(1, attributes)
            latency_histogram.record(simulated_duration_ms, attributes)
            logger.info(
                "Processed remote wakeup request",
                extra={
                    "device_id": device_id,
                    "wakeup_status": wakeup_status,
                    "duration_ms": simulated_duration_ms,
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