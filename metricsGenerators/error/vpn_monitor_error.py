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
SERVICE_NAME = "vpn-monitor"
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
            "component.layer": "infrastructure",
            "component.type": "watchdog",
            "watchdog.target": "vpn-tunnel",
            "watchdog.check.type": "probe",
            "service.location": "onboard",
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

    check_health = meter.create_gauge(name="watchdog.check.health", description="Health state from the last check (1=healthy, 0=unhealthy).", unit="1")
    check_duration = meter.create_histogram(name="watchdog.check.duration", description="Duration of the watchdog health check.", unit="s")
    consecutive_failures = meter.create_gauge(name="watchdog.consecutive_failures", description="Number of consecutive failed checks.", unit="{failure}")
    last_check_ts = meter.create_gauge(name="watchdog.last_check.timestamp", description="Unix timestamp of the last check.", unit="s")
    recovery_count = meter.create_counter(name="watchdog.recovery.count", description="Total recovery events observed.", unit="1")
    packet_loss = meter.create_gauge(name="watchdog.packet.loss", description="Observed packet loss percentage.", unit="%")

    fail_streak = {"train-001": 0, "train-002": 0}
    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            for train in ["train-001", "train-002"]:
                fail_streak[train] += 1
                loss = round(random.uniform(30.0, 60.0), 1)
                attrs = {"vehicle.id": train}

                with tracer.start_as_current_span("vpn_monitor.probe", attributes=attrs):
                    check_health.set(0, attrs)
                    check_duration.record(round(random.uniform(5.0, 30.0), 3), attrs)
                    last_check_ts.set(time.time(), attrs)
                    consecutive_failures.set(fail_streak[train], attrs)
                    packet_loss.set(loss, attrs)

                logger.error(
                    "VPN tunnel DOWN for %s - probe timeout, packet_loss=%.1f%%",
                    train, loss,
                    extra={"train_id": train, "tunnel_up": False, "packet_loss_pct": loss},
                )

            logger.critical(
                "ALL trains reported OFFLINE - no VPN connectivity",
                extra={"trains_offline": 2, "trains_total": 2},
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
