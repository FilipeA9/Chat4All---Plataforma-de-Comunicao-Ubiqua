"""
Message Status Updater Worker (T074)

Consumes message status update events from Kafka, updates message status in
the database, and publishes real-time events to Redis Pub/Sub for WebSocket
notification to connected clients.

Architecture:
    1. Consume from 'message_status_updates' Kafka topic
    2. Update message status in PostgreSQL (SENT, DELIVERED, READ, FAILED)
    3. Publish status change event to Redis Pub/Sub (conversation:{id} channel)
    4. WebSocket connections receive notification in real-time

Status Flow:
    - PENDING (initial) → SENT (after worker processes)
    - SENT → DELIVERED (when channel worker confirms delivery)
    - DELIVERED → READ (when user reads message)
    - Any status → FAILED (on error)

Kafka Message Format:
    {
        "message_id": "uuid",
        "conversation_id": "uuid",
        "new_status": "SENT|DELIVERED|READ|FAILED",
        "user_id": "uuid",  # For READ status - who read the message
        "timestamp": "ISO 8601",
        "details": {}  # Optional error details
    }

Redis Pub/Sub Event Format:
    Channel: conversation:{conversation_id}
    Payload: {
        "type": "MessageStatusUpdated",
        "message_id": "uuid",
        "status": "SENT",
        "updated_at": "ISO 8601"
    }

Usage:
    python -m workers.message_status_updater

Environment Variables:
    DATABASE_URL: PostgreSQL connection string
    KAFKA_BOOTSTRAP_SERVERS: Kafka broker addresses
    REDIS_URL: Redis connection string
"""
import json
import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, Any
from uuid import UUID

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from core.config import settings
from db.database import SessionLocal
from db.repository import Repository
from db.models import MessageStatus
from services.redis_client import get_redis_client
from workers.metrics import messages_processed_total, message_processing_duration_seconds

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Configure structured logging
from core.logging_config import configure_logging
configure_logging(service_name="chat4all-worker-status", level=settings.log_level, enable_json=True)

logger = logging.getLogger(__name__)

# OpenTelemetry tracer
tracer = trace.get_tracer(__name__)
propagator = TraceContextTextMapPropagator()

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


def update_message_status(event: Dict[str, Any]) -> None:
    """
    Update message status in database and publish to Redis.
    
    Args:
        event: Kafka event with message_id, new_status, conversation_id
    """
    message_id = event.get("message_id")
    new_status = event.get("new_status")
    conversation_id = event.get("conversation_id")
    details = event.get("details", {})
    
    if not message_id or not new_status or not conversation_id:
        logger.error(f"Invalid status update event: {event}")
        return
    
    try:
        # Parse status enum
        status_enum = MessageStatus[new_status]
    except KeyError:
        logger.error(f"Invalid status value: {new_status}")
        return
    
    # Update database
    db = SessionLocal()
    try:
        repository = Repository(db)
        
        # Update message status
        repository.update_message_status(
            UUID(message_id),
            status_enum,
            details=details
        )
        
        db.commit()
        logger.info(f"Message {message_id} status updated to {new_status}")
        
        # Publish to Redis Pub/Sub for real-time notification
        redis_client = get_redis_client()
        redis_event = {
            "type": "MessageStatusUpdated",
            "message_id": message_id,
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Add user_id for READ status (who read the message)
        if "user_id" in event:
            redis_event["user_id"] = event["user_id"]
        
        channel = f"conversation:{conversation_id}"
        redis_client.publish(channel, json.dumps(redis_event))
        logger.info(f"Published MessageStatusUpdated to Redis channel {channel}")
        
        # Record success metric
        messages_processed_total.labels(
            worker="message_status_updater",
            channel="status_update",
            status="success"
        ).inc()
        
    except Exception as e:
        logger.error(f"Error updating message status: {e}", exc_info=True)
        db.rollback()
        
        # Record failure metric
        messages_processed_total.labels(
            worker="message_status_updater",
            channel="status_update",
            status="failed"
        ).inc()
        
    finally:
        db.close()


def main():
    """Main worker loop."""
    global shutdown_requested
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Message Status Updater Worker starting...")
    
    try:
        # Create Kafka consumer
        consumer = KafkaConsumer(
            "message_status_updates",
            bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id="message_status_updater_group",
            auto_offset_reset='earliest',
            enable_auto_commit=False,
            max_poll_records=50  # Process in batches for efficiency
        )
        
        logger.info("Message Status Updater Worker connected to Kafka")
        
        # Process messages
        for message in consumer:
            if shutdown_requested:
                logger.info("Shutdown requested, stopping message processing")
                break
            
            try:
                event = message.value
                
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
                    "message_status_updater.process",
                    context=ctx,
                    attributes={
                        "messaging.system": "kafka",
                        "messaging.destination": message.topic,
                        "messaging.kafka.partition": message.partition,
                        "messaging.kafka.offset": message.offset,
                        "messaging.kafka.consumer_group": "message_status_updater_group",
                        "message.id": str(event.get('message_id')),
                        "message.new_status": event.get('new_status'),
                    }
                ):
                    # Track processing duration
                    with message_processing_duration_seconds.labels(
                        worker="message_status_updater"
                    ).time():
                        logger.info(
                            f"Processing status update for message {event.get('message_id')} "
                            f"from partition {message.partition} offset {message.offset}"
                        )
                        update_message_status(event)
                    
                    # Commit offset only after successful processing
                    consumer.commit()
                    logger.debug(f"Committed offset {message.offset} for partition {message.partition}")
                
            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)
                # Do NOT commit offset on failure - message will be reprocessed
        
        # Clean up
        consumer.close()
        logger.info("Message Status Updater Worker stopped gracefully")
        
    except KafkaError as e:
        logger.error(f"Kafka error: {e}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
