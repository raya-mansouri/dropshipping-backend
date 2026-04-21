"""
Webhook Prometheus Metrics
==========================
Prometheus metrics for webhook monitoring and observability.

Uses the shared custom registry from core.metrics to avoid duplicate
registration errors when both modules are loaded in the same process.
"""
import structlog
from prometheus_client import Counter, Histogram, Gauge

from src.core.metrics import registry

logger = structlog.get_logger(__name__)


# =============================================================================
# INCOMING WEBHOOK METRICS
# =============================================================================

# Total incoming webhooks received
WEBHOOK_RECEIVED_TOTAL = Counter(
    "webhook_received_total",
    "Total incoming webhooks received",
    ["platform", "event_type"],
    registry=registry,
)

# Successfully processed webhooks
WEBHOOK_PROCESSED_TOTAL = Counter(
    "webhook_processed_total",
    "Total webhooks successfully processed",
    ["platform", "event_type"],
    registry=registry,
)

# Failed webhook processing
WEBHOOK_FAILED_TOTAL = Counter(
    "webhook_failed_total",
    "Total webhook processing failures",
    ["platform", "event_type", "error_type"],
    registry=registry,
)

# Webhooks moved to DLQ
WEBHOOK_DLQ_TOTAL = Counter(
    "webhook_dlq_total",
    "Total webhooks moved to dead letter queue",
    ["platform", "event_type"],
    registry=registry,
)

# Processing time histogram
WEBHOOK_PROCESSING_SECONDS = Histogram(
    "webhook_processing_seconds",
    "Time spent processing webhooks",
    ["platform", "event_type"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)

# Current DLQ size
WEBHOOK_DLQ_SIZE = Gauge(
    "webhook_dlq_size",
    "Current number of events in webhook dead letter queue",
    ["platform"],
    registry=registry,
)

# Active integrations gauge
WEBHOOK_ACTIVE_INTEGRATIONS = Gauge(
    "webhook_active_integrations",
    "Number of integrations with active webhooks",
    ["platform"],
    registry=registry,
)


# =============================================================================
# OUTGOING WEBHOOK METRICS
# =============================================================================

# Total outgoing webhooks sent
OUTGOING_WEBHOOK_SENT_TOTAL = Counter(
    "outgoing_webhook_sent_total",
    "Total outgoing webhooks sent",
    ["integration_type", "event_type"],
    registry=registry,
)

# Failed outgoing webhooks
OUTGOING_WEBHOOK_FAILED_TOTAL = Counter(
    "outgoing_webhook_failed_total",
    "Total outgoing webhook failures",
    ["integration_type", "event_type", "status_code"],
    registry=registry,
)

# Outgoing webhooks in retry
OUTGOING_WEBHOOK_RETRY_TOTAL = Counter(
    "outgoing_webhook_retry_total",
    "Total outgoing webhook retry attempts",
    ["integration_type", "event_type", "attempt"],
    registry=registry,
)

# Outgoing DLQ size
OUTGOING_DLQ_SIZE = Gauge(
    "outgoing_dlq_size",
    "Current number of events in outgoing webhook dead letter queue",
    registry=registry,
)

# Pending outgoing webhooks
OUTGOING_WEBHOOK_PENDING = Gauge(
    "outgoing_webhook_pending",
    "Number of pending outgoing webhooks",
    registry=registry,
)


# =============================================================================
# SECURITY METRICS
# =============================================================================

# Security events
WEBHOOK_SECURITY_EVENTS = Counter(
    "webhook_security_events_total",
    "Total webhook security events",
    ["event_type", "platform"],
    registry=registry,
)

# Rate limit rejections
WEBHOOK_RATE_LIMIT_REJECTIONS = Counter(
    "webhook_rate_limit_rejections_total",
    "Total webhooks rejected due to rate limiting",
    ["platform"],
    registry=registry,
)

# Signature failures
WEBHOOK_SIGNATURE_FAILURES = Counter(
    "webhook_signature_failures_total",
    "Total webhook signature verification failures",
    ["platform"],
    registry=registry,
)

# IP allowlist rejections
WEBHOOK_IP_REJECTIONS = Counter(
    "webhook_ip_rejections_total",
    "Total webhooks rejected due to IP allowlist",
    ["platform"],
    registry=registry,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def record_webhook_received(platform: str, event_type: str):
    """Record a received webhook."""
    WEBHOOK_RECEIVED_TOTAL.labels(platform=platform, event_type=event_type).inc()


def record_webhook_processed(platform: str, event_type: str, duration_seconds: float):
    """Record a successfully processed webhook."""
    WEBHOOK_PROCESSED_TOTAL.labels(platform=platform, event_type=event_type).inc()
    WEBHOOK_PROCESSING_SECONDS.labels(
        platform=platform, event_type=event_type
    ).observe(duration_seconds)


def record_webhook_failed(platform: str, event_type: str, error_type: str):
    """Record a failed webhook."""
    WEBHOOK_FAILED_TOTAL.labels(
        platform=platform, event_type=event_type, error_type=error_type
    ).inc()


def record_webhook_dlq(platform: str, event_type: str):
    """Record a webhook moved to DLQ."""
    WEBHOOK_DLQ_TOTAL.labels(platform=platform, event_type=event_type).inc()


def record_outgoing_sent(integration_type: str, event_type: str):
    """Record a sent outgoing webhook."""
    OUTGOING_WEBHOOK_SENT_TOTAL.labels(
        integration_type=integration_type, event_type=event_type
    ).inc()


def record_outgoing_failed(
    integration_type: str, event_type: str, status_code: int
):
    """Record a failed outgoing webhook."""
    OUTGOING_WEBHOOK_FAILED_TOTAL.labels(
        integration_type=integration_type,
        event_type=event_type,
        status_code=str(status_code),
    ).inc()


def record_security_event(event_type: str, platform: str):
    """Record a security event."""
    WEBHOOK_SECURITY_EVENTS.labels(
        event_type=event_type, platform=platform
    ).inc()


def update_dlq_size(platform: str, size: int):
    """Update DLQ size gauge."""
    WEBHOOK_DLQ_SIZE.labels(platform=platform).set(size)


def update_active_integrations(platform: str, count: int):
    """Update active integrations gauge."""
    WEBHOOK_ACTIVE_INTEGRATIONS.labels(platform=platform).set(count)


def update_pending_outgoing(count: int):
    """Update pending outgoing gauge."""
    OUTGOING_WEBHOOK_PENDING.set(count)


def update_outgoing_dlq_size(size: int):
    """Update outgoing DLQ size gauge."""
    OUTGOING_DLQ_SIZE.set(size)
