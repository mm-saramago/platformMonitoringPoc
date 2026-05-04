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
SERVICE_NAME = "rabbitmq"
LAYER = "infrastructure"
QUEUE_NAMES = ["wakeup.requests", "wakeup.responses", "telemetry.events"]
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

    queue_depth_gauge = meter.create_gauge(
        name="rabbitmq_queue_depth",
        description="Number of messages currently waiting in the queue.",
        unit="1",
    )
    publish_counter = meter.create_counter(
        name="rabbitmq_messages_published_total",
        description="Total messages published to the broker.",
        unit="1",
    )
    consume_counter = meter.create_counter(
        name="rabbitmq_messages_consumed_total",
        description="Total messages consumed from the broker.",
        unit="1",
    )
    connections_gauge = meter.create_gauge(
        name="rabbitmq_active_connections",
        description="Number of active AMQP connections.",
        unit="1",
    )

    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            connections = random.randint(5, 40)
            connections_gauge.set(connections, {"loop.iteration": iteration})

            for queue in QUEUE_NAMES:
                depth = random.randint(0, 500)
                published = random.randint(10, 200)
                consumed = max(0, published - random.randint(0, 30))
                attributes = {
                    "queue.name": queue,
                    "loop.iteration": iteration,
                }

                with tracer.start_as_current_span("rabbitmq.sample", attributes=attributes):
                    queue_depth_gauge.set(depth, attributes)
                    publish_counter.add(published, attributes)
                    consume_counter.add(consumed, attributes)

                logger.info(
                    "Sampled RabbitMQ queue",
                    extra={
                        "queue": queue,
                        "depth": depth,
                        "published": published,
                        "consumed": consumed,
                        "connections": connections,
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
