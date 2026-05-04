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
SERVICE_NAME = "k8s-node"
LAYER = "infrastructure"
NODE_NAMES = ["wayside-node-1", "wayside-node-2"]
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

    cpu_gauge = meter.create_gauge(
        name="k8s_node_cpu_usage_percent",
        description="Simulated CPU utilization of the K8s node.",
        unit="%",
    )
    memory_gauge = meter.create_gauge(
        name="k8s_node_memory_usage_percent",
        description="Simulated memory utilization of the K8s node.",
        unit="%",
    )
    pods_gauge = meter.create_gauge(
        name="k8s_node_pods_running",
        description="Number of pods currently running on the node.",
        unit="1",
    )
    restarts_counter = meter.create_counter(
        name="k8s_node_pod_restarts_total",
        description="Total simulated pod restarts observed on the node.",
        unit="1",
    )

    iteration = 0
    try:
        while not stop_requested:
            iteration += 1
            for node in NODE_NAMES:
                cpu = round(random.uniform(15.0, 85.0), 2)
                memory = round(random.uniform(30.0, 90.0), 2)
                pods = random.randint(8, 25)
                restarts = 1 if random.random() < 0.1 else 0
                healthy = cpu < 80 and memory < 85
                attributes = {
                    "k8s.node.name": node,
                    "node.healthy": healthy,
                    "loop.iteration": iteration,
                }

                with tracer.start_as_current_span("k8s_node.sample", attributes=attributes):
                    cpu_gauge.set(cpu, attributes)
                    memory_gauge.set(memory, attributes)
                    pods_gauge.set(pods, attributes)
                    if restarts:
                        restarts_counter.add(restarts, attributes)

                logger.info(
                    "Sampled K8s node metrics",
                    extra={
                        "node": node,
                        "cpu_percent": cpu,
                        "memory_percent": memory,
                        "pods_running": pods,
                        "restarts": restarts,
                        "healthy": healthy,
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
