"""
Prometheus Metrics
==================
Application metrics for monitoring and observability
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

registry = CollectorRegistry()

requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=registry,
)

orders_total = Counter(
    "orders_total", "Total orders processed", ["status"], registry=registry
)

inventory_reservations_total = Counter(
    "inventory_reservations_total",
    "Total inventory reservations",
    ["status"],
    registry=registry,
)

webhooks_processed_total = Counter(
    "webhooks_processed_total",
    "Total webhooks processed",
    ["event_type", "status"],
    registry=registry,
)

request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)

order_processing_time_seconds = Histogram(
    "order_processing_time_seconds",
    "Order processing time in seconds",
    ["operation"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0),
    registry=registry,
)

active_connections = Gauge(
    "http_active_connections", "Number of active HTTP connections", registry=registry
)

rate_limit_remaining = Gauge(
    "rate_limit_remaining",
    "Remaining rate limit tokens from external API",
    ["endpoint"],
    registry=registry,
)

queue_depth = Gauge(
    "queue_depth", "Current depth of message queue", ["queue_name"], registry=registry
)

retry_attempts_total = Counter(
    "retry_attempts_total",
    "Total retry attempts by exception type",
    ["exception_type", "attempt"],
    registry=registry,
)

retry_success_total = Counter(
    "retry_success_total",
    "Total successful retries after initial failure",
    ["exception_type"],
    registry=registry,
)

retry_exhausted_total = Counter(
    "retry_exhausted_total",
    "Total retries that exhausted all attempts",
    ["exception_type"],
    registry=registry,
)

product_status_updates_total = Counter(
    "product_status_updates_total",
    "Total product status updates by reason",
    ["old_status", "new_status", "reason"],
    registry=registry,
)


def get_metrics_registry() -> CollectorRegistry:
    """Return the metrics registry for Prometheus scraping."""
    return registry
