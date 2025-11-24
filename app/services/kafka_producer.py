"""
Kafka producer client for publishing messages to topics.
"""
import json
import logging
from typing import Dict, Any
from kafka import KafkaProducer
from kafka.errors import KafkaError
from core.config import settings

logger = logging.getLogger(__name__)


class KafkaProducerClient:
    """Client for publishing messages to Kafka topics."""
    
    def __init__(self):
        """Initialize Kafka producer."""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',  # Wait for all replicas to acknowledge
                retries=3
            )
            logger.info(f"Kafka producer initialized: {settings.kafka_bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            raise
    
    def publish_message(self, topic: str, message: Dict[str, Any]) -> bool:
        """
        Publish a message to a Kafka topic.
        
        Args:
            topic: Kafka topic name
            message: Message dictionary to publish (will be JSON serialized)
            
        Returns:
            True if message was published successfully, False otherwise
        """
        try:
            future = self.producer.send(topic, value=message)
            # Wait for message to be sent (synchronous for reliability)
            record_metadata = future.get(timeout=10)
            logger.info(
                f"Message published to topic '{topic}': "
                f"partition={record_metadata.partition}, offset={record_metadata.offset}"
            )
            return True
        except KafkaError as e:
            logger.error(f"Failed to publish message to topic '{topic}': {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error publishing to Kafka: {e}")
            return False
    
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
