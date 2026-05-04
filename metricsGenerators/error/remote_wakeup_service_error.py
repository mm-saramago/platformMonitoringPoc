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
SERVICE_NAME = "remote-wakeup-service"
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
            "component.layer": "functional",
            "component.type": "onboard",
            "platform.feature": "remote-wakeup",
            "runtime.kind": "agent",
            "service.location": "onboard",
            "vehicle.fleet": "fleet-alpha",
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

    heartbeat_timestamp = meter.create_gauge(name="vehicle.heartbeat.timestamp", description="Timestamp of the last heartbeat from the vehicle.", unit="s")
    message_sync_count = meter.create_counter(name="vehicle.message.sync.count", description="Total messages synchronised from the vehicle.", unit="{message}")
    heartbeat_lag = meter.create_gauge(name="vehicle.heartbeat.lag", description="Seconds since the last successful heartbeat.", unit="s")
    connectivity_state = meter.create_gauge(name="vehicle.connectivity.state", description="Connectivity state of the vehicle (1=online, 0=offline).", unit="1")
    error_count = meter.create_counter(name="vehicle.error.count", description="Total errors reported by the vehicle.", unit="1")
    update_status = meter.create_gauge(name="vehicle.update.status", description="Software update status (0=idle, 1=pending, 2=in-progress).", unit="1")
    message_backlog = meter.create_gauge(name="vehicle.message.backlog", description="Messages queued on the vehicle awaiting sync.", unit="{message}")
    cpu_usage = meter.create_gauge(name="vehicle.cpu.usage", description="Vehicle CPU usage.", unit="%")
    memory_usage = meter.create_gauge(name="vehicle.memory.usage", description="Vehicle memory usage.", unit="%")
    storage_usage = meter.create_gauge(name="vehicle.storage.usage", description="Vehicle storage usage.", unit="%")

    last_heartbeat = time.time() - 300
    backlog = 50
    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            backlog = min(backlog + random.randint(5, 20), 500)
            for train in ["train-001", "train-002"]:
                lag = time.time() - last_heartbeat
                attrs = {"vehicle.id": train}

                with tracer.start_as_current_span("remote_wakeup_service.execute", attributes={"vehicle.id": train, "wakeup.status": "failed"}):
                    pass

                heartbeat_timestamp.set(last_heartbeat, attrs)
                heartbeat_lag.set(round(lag, 1), attrs)
                connectivity_state.set(0, attrs)
                message_backlog.set(backlog, attrs)
                message_sync_count.add(0, {"vehicle.id": train, "wakeup.status": "failed"})
                error_count.add(random.randint(1, 5), {"vehicle.id": train, "error.type": "connectivity_lost"})
                update_status.set(1, attrs)

                cpu_usage.set(round(random.uniform(15.0, 30.0), 1), attrs)
                memory_usage.set(round(random.uniform(40.0, 60.0), 1), attrs)
                storage_usage.set(round(random.uniform(50.0, 65.0), 1), attrs)

                logger.error(
                    "heartbeat timeout for %s, lag=%.0fs - train OFFLINE",
                    train, lag,
                    extra={"train_id": train, "heartbeat_lag_s": round(lag, 1), "backlog": backlog},
                )

            logger.critical(
                "ALL trains OFFLINE - no connectivity, message backlog=%d",
                backlog,
                extra={"trains_offline": 2, "backlog_total": backlog * 2},
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
