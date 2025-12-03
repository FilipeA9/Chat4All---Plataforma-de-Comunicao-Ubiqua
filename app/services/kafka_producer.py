"""
Kafka producer client for publishing messages to topics.
Implements idempotent producer configuration for at-least-once delivery.
Enhanced with OpenTelemetry trace context propagation (T109).
Enhanced with circuit breaker for graceful degradation (T058).
"""
import json
import logging
from typing import Dict, Any, Optional
from kafka import KafkaProducer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import KafkaError, TopicAlreadyExistsError
from core.config import settings
import pybreaker

# OpenTelemetry imports for trace context propagation (T109)
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)

# W3C Trace Context propagator
propagator = TraceContextTextMapPropagator()

# Circuit breaker for Kafka (T058)
# Protects against cascading failures when Kafka is unavailable
kafka_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=5,  # Open circuit after 5 failures
    timeout_duration=60,  # Keep circuit open for 60 seconds
    reset_timeout=30,  # Try half-open after 30 seconds
    name="kafka_producer",
    listeners=[
        lambda breaker, _: logger.warning(f"Circuit breaker {breaker.name} opened - Kafka unavailable"),
        lambda breaker: logger.info(f"Circuit breaker {breaker.name} closed - Kafka restored"),
        lambda breaker: logger.info(f"Circuit breaker {breaker.name} half-open - Testing Kafka connection")
    ]
)


class KafkaProducerClient:
    """Client for publishing messages to Kafka topics with idempotent configuration."""
    
    def __init__(self):
        """
        Initialize Kafka producer with idempotent settings (T011).
        Updated to support 3-broker cluster (T051).
        """
        try:
            # Parse bootstrap servers (T051: support multiple brokers)
            bootstrap_servers = settings.kafka_bootstrap_servers.split(',')
            logger.info(f"Initializing Kafka producer with {len(bootstrap_servers)} brokers: {bootstrap_servers}")
            
            self.producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                # Idempotent producer configuration (T011)
                enable_idempotence=True,  # Ensures exactly-once semantics at producer level
                acks='all',  # Wait for all in-sync replicas to acknowledge (critical for RF=3)
                retries=5,  # Retry failed sends up to 5 times
                max_in_flight_requests_per_connection=5,  # Max unacknowledged requests
                # Additional reliability settings
                compression_type='snappy',  # Compress messages for network efficiency
                linger_ms=10,  # Batch messages for up to 10ms for throughput
                batch_size=32768,  # 32KB batch size
                # Timeout settings for HA cluster (T051)
                request_timeout_ms=30000,  # 30s timeout for produce requests
                metadata_max_age_ms=300000,  # 5 minutes metadata refresh
            )
            logger.info(f"Kafka producer initialized (idempotent, HA cluster)")
            
            # Initialize admin client for topic management
            self.admin_client = KafkaAdminClient(
                bootstrap_servers=bootstrap_servers,
                client_id='chat4all-admin',
                request_timeout_ms=30000
            )
            
            # Create topics with high partitioning (T010)
            self._create_topics()
            
        except KafkaError as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            raise
    
    def _create_topics(self) -> None:
        """
        Create Kafka topics with high partitioning for scalability (T010).
        Updated with replication factor 3 for HA cluster (T050).
        
        Topics:
        - messages: 100 partitions (high throughput message ingestion)
        - file_merge_requests: 50 partitions (file upload completion events)
        - message_status_updates: 50 partitions (read receipts, delivery confirmations)
        - message_processing_dlq: 3 partitions (dead letter queue)
        
        All topics configured with:
        - replication_factor=3 (T050)
        - min.insync.replicas=2 (T050)
        """
        # Detect if running with single broker or HA cluster
        bootstrap_servers = settings.kafka_bootstrap_servers.split(',')
        replication_factor = 3 if len(bootstrap_servers) >= 3 else 1
        
        if replication_factor == 3:
            logger.info("Configuring topics for HA cluster (RF=3, min.insync.replicas=2)")
        else:
            logger.info("Configuring topics for single-broker mode (RF=1)")
        
        topics = [
            NewTopic(
                name="messages",
                num_partitions=100,
                replication_factor=replication_factor,
                topic_configs={'min.insync.replicas': '2'} if replication_factor == 3 else {}
            ),
            NewTopic(
                name="file_merge_requests",
                num_partitions=50,
                replication_factor=replication_factor,
                topic_configs={'min.insync.replicas': '2'} if replication_factor == 3 else {}
            ),
            NewTopic(
                name="message_status_updates",
                num_partitions=50,
                replication_factor=replication_factor,
                topic_configs={'min.insync.replicas': '2'} if replication_factor == 3 else {}
            ),
            NewTopic(
                name="message_processing_dlq",
                num_partitions=3,
                replication_factor=replication_factor,
                topic_configs={
                    'retention.ms': str(7 * 24 * 60 * 60 * 1000),  # 7 days
                    'min.insync.replicas': '2' if replication_factor == 3 else '1'
                }
            ),
        ]
        
        try:
            self.admin_client.create_topics(new_topics=topics, validate_only=False)
            logger.info(f"Created {len(topics)} Kafka topics (RF={replication_factor})")
        except TopicAlreadyExistsError:
            logger.info("Kafka topics already exist, skipping creation")
        except Exception as e:
            logger.warning(f"Could not create topics (may already exist): {e}")
    
    @kafka_circuit_breaker
    def publish_message(self, topic: str, message: Dict[str, Any], partition_key: str = None) -> bool:
        """
        Publish a message to a Kafka topic with optional partition key.
        
        Using a partition key ensures messages with the same key go to the same
        partition, maintaining ordering. For message events, use conversation_id
        as the partition key to ensure messages within a conversation are ordered.
        
        Includes OpenTelemetry trace context propagation via Kafka headers (T109).
        Protected by circuit breaker (T058) - raises CircuitBreakerError when open.
        
        Args:
            topic: Kafka topic name
            message: Message dictionary to publish (will be JSON serialized)
            partition_key: Optional partition key for message ordering (e.g., conversation_id)
            
        Returns:
            True if message was published successfully, False otherwise
            
        Raises:
            pybreaker.CircuitBreakerError: When circuit is open (Kafka unavailable)
        """
        try:
            # Inject trace context into Kafka headers (T109)
            headers = []
            carrier = {}
            propagator.inject(carrier)
            
            # Convert carrier dict to Kafka headers format (list of tuples)
            for key, value in carrier.items():
                headers.append((key, value.encode('utf-8')))
            
            # Create span for Kafka publish operation
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("kafka.publish") as span:
                span.set_attribute("messaging.system", "kafka")
                span.set_attribute("messaging.destination", topic)
                span.set_attribute("messaging.destination_kind", "topic")
                if partition_key:
                    span.set_attribute("messaging.kafka.partition_key", partition_key)
                
                # Publish with partition key and trace headers
                future = self.producer.send(
                    topic, 
                    value=message,
                    key=partition_key.encode('utf-8') if partition_key else None,
                    headers=headers  # Include trace context headers
                )
                
                # Wait for message to be sent (synchronous for reliability)
                record_metadata = future.get(timeout=10)
                
                span.set_attribute("messaging.kafka.partition", record_metadata.partition)
                span.set_attribute("messaging.kafka.offset", record_metadata.offset)
                
                logger.info(
                    f"Message published to topic '{topic}': "
                    f"partition={record_metadata.partition}, offset={record_metadata.offset}, "
                    f"key={partition_key}"
                )
                return True
                
        except KafkaError as e:
            logger.error(f"Failed to publish message to topic '{topic}': {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error publishing to Kafka: {e}")
            return False
    
    def get_cluster_metadata(self) -> Dict[str, Any]:
        """
        Get Kafka cluster metadata for health monitoring (T052).
        
        Returns metadata about brokers, topics, and partition status.
        Used by workers/metrics.py for monitoring under-replicated partitions.
        
        Returns:
            Dictionary with cluster metadata:
            - brokers: List of broker information
            - topics: Topic metadata including partition details
            - under_replicated_partitions: Count of unhealthy partitions
        """
        try:
            # Get cluster metadata
            metadata = self.producer.cluster
            
            # Extract broker information
            brokers = []
            for broker_id in metadata.brokers():
                broker = metadata.broker_metadata(broker_id)
                brokers.append({
                    'id': broker_id,
                    'host': broker.host,
                    'port': broker.port,
                    'rack': broker.rack
                })
            
            # Extract topic information
            topics = {}
            under_replicated_count = 0
            
            for topic in metadata.topics():
                topic_metadata = metadata.available_partitions_for_topic(topic)
                partitions_info = []
                
                for partition in topic_metadata:
                    partition_info = {
                        'partition': partition,
                        'leader': metadata.leader_for_partition(topic, partition),
                        'replicas': metadata.replicas_for_partition(topic, partition),
                        'isr': metadata.isr_for_partition(topic, partition),
                    }
                    
                    # Check if partition is under-replicated (T052)
                    if partition_info['isr'] and partition_info['replicas']:
                        if len(partition_info['isr']) < len(partition_info['replicas']):
                            under_replicated_count += 1
                            partition_info['under_replicated'] = True
                    
                    partitions_info.append(partition_info)
                
                topics[topic] = {
                    'partitions': len(partitions_info),
                    'partition_details': partitions_info
                }
            
            return {
                'brokers': brokers,
                'broker_count': len(brokers),
                'topics': topics,
                'topic_count': len(topics),
                'under_replicated_partitions': under_replicated_count,
                'cluster_id': metadata.cluster_id() if hasattr(metadata, 'cluster_id') else None
            }
            
        except Exception as e:
            logger.error(f"Failed to get cluster metadata: {e}")
            return {
                'error': str(e),
                'brokers': [],
                'broker_count': 0,
                'topics': {},
                'topic_count': 0,
                'under_replicated_partitions': 0
            }
    
    def close(self) -> None:
        """Close the Kafka producer connection."""
        if self.producer:
            self.producer.close()
            logger.info("Kafka producer closed")


# Global Kafka producer instance (initialized on first use)
_kafka_producer: KafkaProducerClient = None


def get_kafka_producer() -> KafkaProducerClient:
    """
    Get or create global Kafka producer instance.
    
    Returns:
        KafkaProducerClient instance
    """
    global _kafka_producer
    if _kafka_producer is None:
        _kafka_producer = KafkaProducerClient()
    return _kafka_producer
