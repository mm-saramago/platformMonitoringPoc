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
SERVICE_NAME = "vpn-terminator-ground"
LAYER = "infrastructure"
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
            "deployment.environment": "local",
            "component.layer": LAYER,
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

    active_tunnels_gauge = meter.create_gauge(
        name="vpn_terminator_active_tunnels",
        description="Number of VPN tunnels currently terminated on the ground.",
        unit="1",
    )
    throughput_gauge = meter.create_gauge(
        name="vpn_terminator_throughput_mbps",
        description="Aggregate throughput across all VPN tunnels in Mbps.",
        unit="Mbit/s",
    )
    handshake_counter = meter.create_counter(
        name="vpn_terminator_handshakes_total",
        description="Total VPN handshake attempts handled by the terminator.",
        unit="1",
    )

    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            tunnels = random.randint(20, 80)
            throughput = round(random.uniform(50.0, 800.0), 2)
            handshakes = random.randint(1, 10)
            handshake_status = random.choices(["success", "failed"], weights=[9, 1])[0]
            attributes = {
                "handshake.status": handshake_status,
                "loop.iteration": iteration,
            }

            with tracer.start_as_current_span("vpn_terminator.sample", attributes=attributes):
                active_tunnels_gauge.set(tunnels, {"loop.iteration": iteration})
                throughput_gauge.set(throughput, {"loop.iteration": iteration})
                handshake_counter.add(handshakes, attributes)

            logger.info(
                "Sampled VPN terminator state",
                extra={
                    "active_tunnels": tunnels,
                    "throughput_mbps": throughput,
                    "handshakes": handshakes,
                    "handshake_status": handshake_status,
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
