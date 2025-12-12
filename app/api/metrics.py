"""
Prometheus metrics for API service.

Tracks API performance, WebSocket connections, and business metrics.
"""
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

# Create registry
registry = CollectorRegistry()

# WebSocket connection metrics
websocket_connections_active = Gauge(
    "websocket_connections_active",
    "Number of active WebSocket connections",
    labelnames=["instance"],
    registry=registry
)

websocket_connections_total = Counter(
    "websocket_connections_total",
    "Total number of WebSocket connections established",
    labelnames=["instance"],
    registry=registry
)

websocket_disconnections_total = Counter(
    "websocket_disconnections_total",
    "Total number of WebSocket disconnections",
    labelnames=["instance", "reason"],
    registry=registry
)

websocket_message_latency_seconds = Histogram(
    "websocket_message_latency_seconds",
    "Latency of WebSocket message delivery",
    labelnames=["message_type"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0],
    registry=registry
)

websocket_messages_sent_total = Counter(
    "websocket_messages_sent_total",
    "Total number of messages sent via WebSocket",
    labelnames=["message_type", "instance"],
    registry=registry
)

websocket_messages_received_total = Counter(
    "websocket_messages_received_total",
    "Total number of messages received via WebSocket",
    labelnames=["action", "instance"],
    registry=registry
)

websocket_subscriptions_total = Gauge(
    "websocket_subscriptions_total",
    "Total number of active conversation subscriptions",
    labelnames=["instance"],
    registry=registry
)

websocket_users_connected = Gauge(
    "websocket_users_connected",
    "Number of unique users currently connected",
    labelnames=["instance"],
    registry=registry
)

# API business metrics
messages_created_total = Counter(
    "messages_created_total",
    "Total number of messages created",
    labelnames=["conversation_type", "instance"],
    registry=registry
)

message_processing_duration_seconds = Histogram(
    "message_processing_duration_seconds",
    "Time to process message from API to outbox",
    labelnames=["status", "instance"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0],
    registry=registry
)

outbox_pending_events = Gauge(
    "outbox_pending_events",
    "Number of unpublished events in outbox",
    labelnames=["aggregate_type", "instance"],
    registry=registry
)

# Authentication metrics
auth_requests_total = Counter(
    "auth_requests_total",
    "Total number of authentication requests",
    labelnames=["type", "status", "instance"],
    registry=registry
)

auth_token_validations_total = Counter(
    "auth_token_validations_total",
    "Total number of token validation attempts",
    labelnames=["type", "status", "instance"],
    registry=registry
)

# File upload metrics
file_uploads_initiated_total = Counter(
    "file_uploads_initiated_total",
    "Total number of file uploads initiated",
    labelnames=["instance"],
    registry=registry
)

file_uploads_completed_total = Counter(
    "file_uploads_completed_total",
    "Total number of file uploads completed",
    labelnames=["status", "instance"],
    registry=registry
)

file_upload_size_bytes = Histogram(
    "file_upload_size_bytes",
    "Size of uploaded files in bytes",
    labelnames=["instance"],
    buckets=[1024, 10240, 102400, 1048576, 10485760, 104857600, 1073741824, 2147483648],
    registry=registry
)


def update_websocket_metrics(connection_manager):
    """
    Update WebSocket metrics from connection manager state.
    
    Should be called periodically (e.g., every 10 seconds) to keep
    metrics current.
    
    Args:
        connection_manager: ConnectionManager instance
    """
    # Update connection count
    total_connections = connection_manager.get_connection_count()
    websocket_connections_active.labels(instance="api").set(total_connections)
    
    # Update unique users count
    unique_users = connection_manager.get_user_count()
    websocket_users_connected.labels(instance="api").set(unique_users)
    
    # Update subscription count
    total_subscriptions = sum(
        len(subs) for subs in connection_manager.connection_subscriptions.values()
    )
    websocket_subscriptions_total.labels(instance="api").set(total_subscriptions)
