"""
Message Router Worker
Consumes messages from 'message_processing' topic and routes them to
appropriate channel topics based on the channels array.
Enhanced with OpenTelemetry trace context extraction (T110).
"""
import json
import logging
import signal
import sys
from prometheus_client import start_http_server
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from core.config import settings

# OpenTelemetry imports (T110)
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Configure structured logging
from core.logging_config import configure_logging
configure_logging(service_name="chat4all-worker-router", level=settings.log_level, enable_json=True)

logger = logging.getLogger(__name__)

# W3C Trace Context propagator
propagator = TraceContextTextMapPropagator()
tracer = trace.get_tracer(__name__)

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


def validate_file_message(message_data: dict) -> bool:
    """
    Validate file message by checking if file exists in MinIO.
    
    Args:
        message_data: Message data with payload
        
    Returns:
        True if file is valid or message is not a file message, False otherwise
    """
    payload = message_data.get("payload", {})
    
    # If not a file message, no validation needed
    if payload.get("type") != "file":
        return True
    
    file_id = payload.get("file_id")
    if not file_id:
        logger.error("File message missing file_id")
        return False
    
    try:
        from services.minio_client import get_minio_client
        from db.database import SessionLocal
        from db.repository import Repository
        from uuid import UUID
        
        # Check if file exists in database
        db = SessionLocal()
        repository = Repository(db)
        file_metadata = repository.get_file_metadata(UUID(file_id))
        db.close()
        
        if not file_metadata:
            logger.error(f"File metadata not found for file_id: {file_id}")
            return False
        
        if file_metadata.status.value != "COMPLETED":
            logger.error(f"File upload not completed for file_id: {file_id}")
            return False
        
        # Check if file exists in MinIO
        minio_client = get_minio_client()
        if not minio_client.object_exists(file_metadata.minio_object_name):
            logger.error(f"File not found in MinIO: {file_metadata.minio_object_name}")
            return False
        
        logger.info(f"File validated successfully: {file_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error validating file message: {e}")
        return False


def mark_message_failed(message_id: str) -> None:
    """
    Mark message as FAILED in database.
    
    Args:
        message_id: UUID of the message
    """
    try:
        from db.database import SessionLocal
        from db.repository import Repository
        from db.models import MessageStatus
        from uuid import UUID
        
        db = SessionLocal()
        repository = Repository(db)
        repository.update_message_status(
            UUID(message_id),
            MessageStatus.FAILED,
            details={"reason": "File validation failed"}
        )
        db.close()
        logger.info(f"Message {message_id} marked as FAILED")
    except Exception as e:
        logger.error(f"Error marking message as failed: {e}")


def route_message(producer: KafkaProducer, message_data: dict) -> None:
    """
    Route message to appropriate channel topics based on channels array.
    Validates file messages before routing.
    
    Args:
        producer: Kafka producer instance
        message_data: Message data including channels array
    """
    channels = message_data.get("channels", [])
    message_id = message_data.get("message_id")
    
    # Validate file message if applicable
    if not validate_file_message(message_data):
        logger.error(f"Message {message_id}: file validation failed, marking as FAILED")
        mark_message_failed(message_id)
        return
    
    topics_to_publish = []
    
    # Determine which topics to publish to
    if "all" in channels:
        topics_to_publish = ["whatsapp_outgoing", "instagram_outgoing"]
        logger.info(f"Message {message_id}: routing to all channels")
    else:
        if "whatsapp" in channels:
            topics_to_publish.append("whatsapp_outgoing")
        if "instagram" in channels:
            topics_to_publish.append("instagram_outgoing")
        logger.info(f"Message {message_id}: routing to {', '.join(topics_to_publish)}")
    
    # Use conversation_id as partition key to ensure message ordering within conversations
    conversation_id = str(message_data.get("conversation_id", ""))
    partition_key = f"conversation:{conversation_id}" if conversation_id else None
    
    # Publish to each topic
    for topic in topics_to_publish:
        try:
            future = producer.send(
                topic, 
                value=message_data,
                key=partition_key  # Ensure messages go to same partition
            )
            future.get(timeout=10)  # Wait for confirmation
            logger.info(f"Message {message_id} published to {topic} with key {partition_key}")
        except KafkaError as e:
            logger.error(f"Failed to publish message {message_id} to {topic}: {e}")


def main():
    """Main worker loop."""
    global shutdown_requested
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Message Router Worker starting...")

    print("Iniciando servidor de métricas Prometheus na porta 8000...")
    start_http_server(8000)
    
    try:
        # Create Kafka consumer with manual offset commit for message ordering
        consumer = KafkaConsumer(
            "message_processing",
            bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id="message_router_group",
            auto_offset_reset='earliest',
            # Disable auto-commit for better control over message processing
            enable_auto_commit=False,
            # Ensure messages within same partition are processed in order
            max_poll_records=10  # Process in small batches to reduce lag
        )
        
        # Create Kafka producer with partition key support for ordering
        producer = KafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            acks='all',
            retries=3
        )
        
        logger.info("Message Router Worker connected to Kafka (manual commit mode)")
        
        # Process messages
        for message in consumer:
            if shutdown_requested:
                logger.info("Shutdown requested, stopping message processing")
                break
            
            try:
                message_data = message.value
                
                # Extract trace context from Kafka headers
                carrier = {}
                if message.headers:
                    for key, value in message.headers:
                        if value:
                            carrier[key] = value.decode('utf-8') if isinstance(value, bytes) else value
                
                # Extract parent context from headers
                ctx = propagator.extract(carrier=carrier)
                
                # Create a new span as a child of the extracted context
                with tracer.start_as_current_span(
                    "message_router.process",
                    context=ctx,
                    attributes={
                        "messaging.system": "kafka",
                        "messaging.destination": message.topic,
                        "messaging.kafka.partition": message.partition,
                        "messaging.kafka.offset": message.offset,
                        "messaging.kafka.consumer_group": "message_router_group",
                        "message.id": str(message_data.get('message_id')),
                        "message.channels": str(message_data.get('channels', [])),
                    }
                ):
                    logger.info(
                        f"Processing message {message_data.get('message_id')} "
                        f"from partition {message.partition} offset {message.offset}"
                    )
                    route_message(producer, message_data)
                    
                    # Commit offset only after successful processing
                    # This ensures at-least-once delivery and maintains ordering
                    consumer.commit()
                    logger.debug(f"Committed offset {message.offset} for partition {message.partition}")
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                # Do NOT commit offset on failure - message will be reprocessed
        
        # Clean up
        consumer.close()
        producer.close()
        logger.info("Message Router Worker stopped gracefully")
        
    except KafkaError as e:
        logger.error(f"Kafka error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
