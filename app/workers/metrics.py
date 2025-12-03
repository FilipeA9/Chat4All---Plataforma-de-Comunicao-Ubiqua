"""
Worker Metrics Module.

Provides Prometheus metrics for worker processes including:
- Outbox poller metrics
- DLQ message counters
- Message processing metrics
- Kafka consumer lag

Usage:
    from workers.metrics import outbox_published_total, dlq_messages_total
    
    outbox_published_total.inc()
    dlq_messages_total.labels(reason="kafka_timeout", aggregate_type="message").inc()
"""
from prometheus_client import Counter, Gauge, Histogram, generate_latest, REGISTRY

# Outbox Poller Metrics
outbox_published_total = Counter(
    'outbox_published_total',
    'Total number of outbox events successfully published to Kafka'
)

outbox_failed_total = Counter(
    'outbox_failed_total',
    'Total number of outbox events that failed after all retries',
    ['aggregate_type', 'event_type']
)

outbox_pending_events = Gauge(
    'outbox_pending_events',
    'Current number of unpublished events in outbox table'
)

outbox_publish_duration_seconds = Histogram(
    'outbox_publish_duration_seconds',
    'Time spent publishing single outbox event to Kafka',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# Dead Letter Queue Metrics
dlq_messages_total = Counter(
    'dlq_messages_total',
    'Total number of messages published to Dead Letter Queue',
    ['reason', 'aggregate_type']
)

# Message Processing Metrics
messages_processed_total = Counter(
    'messages_processed_total',
    'Total number of messages processed by workers',
    ['worker', 'channel', 'status']
)

message_processing_duration_seconds = Histogram(
    'message_processing_duration_seconds',
    'Time spent processing single message',
    ['worker', 'channel'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Kafka Consumer Metrics
kafka_consumer_lag = Gauge(
    'kafka_consumer_lag',
    'Kafka consumer lag per topic and partition',
    ['topic', 'partition', 'consumer_group']
)

kafka_consumer_offset = Gauge(
    'kafka_consumer_offset',
    'Current Kafka consumer offset',
    ['topic', 'partition', 'consumer_group']
)

# Upload Garbage Collection Metrics
UPLOADS_CLEANED_TOTAL = Counter(
    'uploads_cleaned_total',
    'Total number of abandoned uploads cleaned up by garbage collector'
)

CLEANUP_DURATION_SECONDS = Histogram(
    'cleanup_duration_seconds',
    'Time spent running garbage collection',
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
)

# Kafka Broker Health Metrics (T052)
kafka_broker_online = Gauge(
    'kafka_broker_online',
    'Kafka broker availability (1=online, 0=offline)',
    ['broker_id', 'host', 'port']
)

kafka_under_replicated_partitions = Gauge(
    'kafka_under_replicated_partitions',
    'Number of under-replicated partitions in Kafka cluster',
    ['topic']
)

kafka_offline_partitions = Gauge(
    'kafka_offline_partitions',
    'Number of offline partitions in Kafka cluster',
    ['topic']
)

kafka_isr_shrink_events = Counter(
    'kafka_isr_shrink_events',
    'Number of ISR (In-Sync Replicas) shrink events detected',
    ['topic', 'partition']
)

kafka_cluster_brokers = Gauge(
    'kafka_cluster_brokers',
    'Total number of brokers in Kafka cluster'
)

kafka_cluster_topics = Gauge(
    'kafka_cluster_topics',
    'Total number of topics in Kafka cluster'
)


def update_kafka_broker_health(metadata: dict) -> None:
    """
    Update Kafka broker health metrics from cluster metadata (T052).
    
    Should be called periodically (e.g., every 30 seconds) to monitor broker health.
    Detects:
    - Offline brokers
    - Under-replicated partitions
    - ISR shrink events
    
    Args:
        metadata: Cluster metadata from KafkaProducerClient.get_cluster_metadata()
    """
    # Update broker count
    kafka_cluster_brokers.set(metadata.get('broker_count', 0))
    kafka_cluster_topics.set(metadata.get('topic_count', 0))
    
    # Update broker online status
    for broker in metadata.get('brokers', []):
        kafka_broker_online.labels(
            broker_id=str(broker['id']),
            host=broker['host'],
            port=str(broker['port'])
        ).set(1)  # If we can fetch metadata, broker is online
    
    # Update under-replicated partitions per topic
    topics = metadata.get('topics', {})
    for topic_name, topic_info in topics.items():
        under_replicated_count = 0
        offline_count = 0
        
        for partition in topic_info.get('partition_details', []):
            # Check if partition is under-replicated
            if partition.get('under_replicated', False):
                under_replicated_count += 1
            
            # Check if partition is offline (no leader)
            if partition.get('leader') is None:
                offline_count += 1
        
        # Set metrics per topic
        kafka_under_replicated_partitions.labels(topic=topic_name).set(under_replicated_count)
        kafka_offline_partitions.labels(topic=topic_name).set(offline_count)
    
    # Set total under-replicated partitions
    total_under_replicated = metadata.get('under_replicated_partitions', 0)
    kafka_under_replicated_partitions.labels(topic='__total__').set(total_under_replicated)


def get_metrics() -> bytes:
    """
    Get Prometheus metrics in exposition format.
    
    Returns:
        bytes: Metrics in Prometheus text format
    """
    return generate_latest(REGISTRY)
