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
SERVICE_NAME = "mqtt-broker"
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

    connected_clients_gauge = meter.create_gauge(
        name="mqtt_broker_connected_clients",
        description="Number of MQTT clients currently connected to the broker.",
        unit="1",
    )
    messages_received_counter = meter.create_counter(
        name="mqtt_broker_messages_received_total",
        description="Total MQTT messages received by the broker.",
        unit="1",
    )
    messages_sent_counter = meter.create_counter(
        name="mqtt_broker_messages_sent_total",
        description="Total MQTT messages forwarded to subscribers.",
        unit="1",
    )
    dropped_counter = meter.create_counter(
        name="mqtt_broker_messages_dropped_total",
        description="MQTT messages dropped because of QoS or backpressure.",
        unit="1",
    )

    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            clients = random.randint(20, 200)
            received = random.randint(50, 500)
            sent = max(0, received - random.randint(0, 20))
            dropped = random.randint(0, 5)
            attributes = {"loop.iteration": iteration}

            with tracer.start_as_current_span("mqtt_broker.sample", attributes=attributes):
                connected_clients_gauge.set(clients, attributes)
                messages_received_counter.add(received, attributes)
                messages_sent_counter.add(sent, attributes)
                if dropped:
                    dropped_counter.add(dropped, attributes)

            logger.info(
                "Sampled MQTT broker activity",
                extra={
                    "connected_clients": clients,
                    "messages_received": received,
                    "messages_sent": sent,
                    "messages_dropped": dropped,
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
