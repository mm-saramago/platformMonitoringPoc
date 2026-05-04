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
            "deployment.environment": "local",
            "component.layer": "infrastructure",
            "component.type": "watchdog",
            "watchdog.target": "vpn-tunnel",
            "watchdog.target.category": "network",
            "watchdog.check.type": "probe",
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
    failover_triggered = meter.create_counter(
        name="watchdog.failover.triggered",
        description="Total failover events triggered.",
        unit="1",
    )
    packet_loss = meter.create_gauge(
        name="watchdog.packet.loss",
        description="Observed packet loss percentage.",
        unit="%",
    )
    tcp_conn_duration = meter.create_histogram(
        name="watchdog.tcp.connection.duration",
        description="Duration of TCP connection probes.",
        unit="s",
    )
    # Supplementary
    active_tunnels = meter.create_gauge(
        name="vpn.terminator.active_tunnels",
        description="Number of VPN tunnels currently terminated on the ground.",
        unit="{tunnel}",
    )
    throughput_mbps = meter.create_gauge(
        name="vpn.terminator.throughput_mbps",
        description="Aggregate throughput across all VPN tunnels in Mbps.",
        unit="{Mbit/s}",
    )

    fail_streak = 0
    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            tunnels = random.randint(20, 80)
            throughput = round(random.uniform(50.0, 800.0), 2)
            healthy = random.random() > 0.08
            dur = round(random.uniform(0.01, 0.20), 4)
            tcp_dur = round(random.uniform(0.005, 0.15), 4)
            loss = round(random.uniform(0.0, 5.0), 2) if not healthy else round(random.uniform(0.0, 0.5), 2)

            with tracer.start_as_current_span("vpn_terminator.sample"):
                check_duration.record(dur)
                tcp_conn_duration.record(tcp_dur)
                check_health.set(1 if healthy else 0)
                last_check_ts.set(time.time())
                packet_loss.set(loss)
                active_tunnels.set(tunnels)
                throughput_mbps.set(throughput)

                if healthy:
                    if fail_streak > 0:
                        recovery_count.add(1)
                    fail_streak = 0
                else:
                    fail_streak += 1
                    if fail_streak >= 3 and random.random() < 0.3:
                        failover_triggered.add(1)

                consecutive_failures.set(fail_streak)

            logger.info(
                "Sampled VPN terminator state",
                extra={
                    "active_tunnels": tunnels,
                    "throughput_mbps": throughput,
                    "healthy": healthy,
                    "packet_loss_pct": loss,
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
