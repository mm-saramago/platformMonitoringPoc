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
            #General attributes
            "sub_component.name": SERVICE_NAME, 
            "component.type": "crosscutting-service",
            "fleet.name": "QNGR-OrbifloNG-PROD",
            "feature.name": "crosscutting-infrastructure",
            "feature.type": "crosscutting-component-infra",
            "component.name": "infrastructure-compute",
            "service.location": "wayside",
            #Lower level attributes
            "service.namespace": "sample-apps",
            "service.version": "1.0.0",
            "deployment.environment": "local",
            "component.layer": "infrastructure",
            "component.subtype": "message-broker",
            "messaging.system": "rabbitmq",
           
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

    # Traffic
    publish_messages = meter.create_counter(
        name="messaging.publish.messages",
        description="Total messages published to the broker.",
        unit="{message}",
    )
    process_messages = meter.create_counter(
        name="messaging.process.messages",
        description="Total messages consumed from the broker.",
        unit="{message}",
    )
    # Saturation
    queue_depth = meter.create_gauge(
        name="messaging.queue.depth",
        description="Number of messages waiting in the queue.",
        unit="{message}",
    )
    consumer_lag = meter.create_gauge(
        name="messaging.consumer.lag",
        description="Consumer lag in number of messages.",
        unit="{message}",
    )
    consumer_lag_seconds = meter.create_gauge(
        name="messaging.consumer.lag_seconds",
        description="Consumer lag in seconds.",
        unit="s",
    )
    # Latency
    publish_duration = meter.create_histogram(
        name="messaging.publish.duration",
        description="Time to publish a message.",
        unit="s",
    )
    process_duration = meter.create_histogram(
        name="messaging.process.duration",
        description="Time to process a consumed message.",
        unit="s",
    )
    component_health = meter.create_gauge(
        name="component.health.ratio",
        description="Overall component health ratio (1=healthy, 0.5=degraded, 0=unhealthy).",
        unit="1",
    )

    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            for queue in QUEUE_NAMES:
                depth = random.randint(0, 500)
                published = random.randint(10, 200)
                consumed = max(0, published - random.randint(0, 30))
                lag_msgs = max(0, depth - consumed)
                lag_s = round(lag_msgs * random.uniform(0.01, 0.1), 2)
                pub_dur = round(random.uniform(0.001, 0.05), 4)
                proc_dur = round(random.uniform(0.002, 0.08), 4)
                attrs = {"messaging.destination.name": queue}
                component_health.set(1 if depth < 2000 else 0, {})

                with tracer.start_as_current_span("rabbitmq.sample", attributes=attrs):
                    queue_depth.set(depth, attrs)
                    publish_messages.add(published, attrs)
                    process_messages.add(consumed, attrs)
                    consumer_lag.set(lag_msgs, attrs)
                    consumer_lag_seconds.set(lag_s, attrs)
                    publish_duration.record(pub_dur, attrs)
                    process_duration.record(proc_dur, attrs)

                logger.info(
                    "Sampled RabbitMQ queue",
                    extra={
                        "queue": queue,
                        "depth": depth,
                        "published": published,
                        "consumed": consumed,
                        "consumer_lag": lag_msgs,
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
