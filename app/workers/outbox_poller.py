"""
Outbox Poller Worker.

Implements the Transactional Outbox pattern by polling unpublished events
from the outbox_events table and reliably publishing them to Kafka.

This worker guarantees at-least-once delivery: even if Kafka is temporarily
unavailable, messages are safely persisted in the database and will be
published when Kafka becomes available again.

Architecture:
    1. Poll outbox_events table every 500ms for unpublished events
    2. Publish each event to Kafka (topic based on event_type)
    3. Mark event as published in database
    4. Implement exponential backoff for transient failures
    5. After 3 retries, log error and move to next event (DLQ handling in separate task)

Usage:
    python -m workers.outbox_poller

Environment Variables:
    DATABASE_URL: PostgreSQL connection string
    KAFKA_BOOTSTRAP_SERVERS: Kafka broker addresses
    OUTBOX_POLL_INTERVAL_MS: Polling interval (default: 500ms)
    OUTBOX_BATCH_SIZE: Events per batch (default: 100)
    OUTBOX_MAX_RETRIES: Max retry attempts (default: 3)
"""
import asyncio
import logging
import time
import sys
from typing import List
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from kafka import KafkaProducer
from kafka.errors import KafkaError
import json

from core.config import settings
from db.models import OutboxEvent
from db.repository import Repository
from workers.metrics import (
    outbox_published_total, outbox_failed_total, dlq_messages_total,
    outbox_publish_duration_seconds, outbox_pending_events
)
from services.redis_client import get_redis_client

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Configure structured logging
from core.logging_config import configure_logging
configure_logging(service_name="chat4all-worker-outbox", level=settings.log_level, enable_json=True)

logger = logging.getLogger(__name__)

# OpenTelemetry tracer
tracer = trace.get_tracer(__name__)
propagator = TraceContextTextMapPropagator()

# Configuration
POLL_INTERVAL_SECONDS = 0.5  # 500ms
BATCH_SIZE = 100  # Events per poll
MAX_RETRIES = 3  # Maximum retry attempts before giving up
INITIAL_BACKOFF_SECONDS = 1  # Initial backoff delay


class OutboxPoller:
    """
    Outbox Poller Worker for reliable Kafka event publishing.
    
    Implements the polling mechanism of the Transactional Outbox pattern.
    Continuously polls the outbox_events table for unpublished events and
    publishes them to Kafka with retry logic.
    """
    
    def __init__(self):
        """Initialize outbox poller with database and Kafka connections."""
        # Setup database connection
        self.engine = create_engine(
            settings.database_url,
            pool_size=5,  # Smaller pool for worker
            max_overflow=5,
            pool_pre_ping=True
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Setup Kafka producer
        self.producer = None
        self._init_kafka_producer()
        
        # Metrics
        self.events_published = 0
        self.events_failed = 0
        self.last_poll_time = None
        
        logger.info("OutboxPoller initialized successfully")
    
    def _init_kafka_producer(self):
        """Initialize Kafka producer with idempotent configuration."""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                # Idempotent producer configuration
                enable_idempotence=True,
                acks='all',  # Wait for all in-sync replicas
                retries=5,
                max_in_flight_requests_per_connection=5,
                # Timeout configuration
                request_timeout_ms=30000,
                # Compression for better throughput
                compression_type='snappy'
            )
            logger.info("Kafka producer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            raise
    
    def _determine_kafka_topic(self, event_type: str) -> str:
        """
        Determine Kafka topic based on event type.
        
        Args:
            event_type: Event type (e.g., 'message.created', 'file.uploaded')
            
        Returns:
            Kafka topic name
        """
        # Map event types to Kafka topics
        topic_mapping = {
            'message.created': 'message_events',
            'message.updated': 'message_events',
            'file.uploaded': 'file_events',
            'file.completed': 'file_events',
            'conversation.created': 'conversation_events',
            'conversation.updated': 'conversation_events'
        }
        
        return topic_mapping.get(event_type, 'default_events')
    
    def _get_partition_key(self, event: OutboxEvent) -> str:
        """
        Get partition key for Kafka message to ensure ordering.
        
        For message events, use conversation_id to ensure messages in the
        same conversation go to the same partition (maintains ordering).
        
        Args:
            event: Outbox event
            
        Returns:
            Partition key as string
        """
        if event.aggregate_type == 'message':
            # Extract conversation_id from payload for partitioning
            conversation_id = event.payload.get('conversation_id')
            if conversation_id:
                return f"conversation:{conversation_id}"
        
        # Default: partition by aggregate_id
        return str(event.aggregate_id)
    
    def _publish_to_dlq(self, event: OutboxEvent, error_message: str):
        """
        Publish failed event to Dead Letter Queue (DLQ).
        
        After MAX_RETRIES exhausted, events are published to the DLQ
        for manual investigation and potential replay.
        
        Args:
            event: Failed outbox event
            error_message: Final error message from last retry
        """
        try:
            dlq_message = {
                'dlq_id': str(event.id),
                'original_event_id': str(event.id),
                'aggregate_type': event.aggregate_type,
                'aggregate_id': str(event.aggregate_id),
                'event_type': event.event_type,
                'payload': event.payload,
                'failure_reason': error_message,
                'retry_count': event.version,
                'created_at': event.created_at.isoformat(),
                'failed_at': datetime.utcnow().isoformat()
            }
            
            # Publish to DLQ topic
            future = self.producer.send(
                topic='message_processing_dlq',
                key=str(event.aggregate_id),
                value=dlq_message
            )
            
            # Wait for confirmation
            future.get(timeout=10)
            
            logger.info(
                f"Event {event.id} published to DLQ after {event.version} retries"
            )
            
            # Mark as published to prevent reprocessing
            # (even though it went to DLQ, we don't want to retry again)
            repository = Repository(self.SessionLocal())
            repository.mark_outbox_event_published(event.id)
            
        except Exception as dlq_error:
            logger.error(
                f"CRITICAL: Failed to publish event {event.id} to DLQ: {dlq_error}. "
                f"Event data: {event.payload}"
            )
    
    def _publish_event_to_redis(self, event: OutboxEvent):
        """
        Publish event to Redis Pub/Sub for real-time WebSocket notifications.
        
        Publishes to conversation:{id} or user:{id} channels based on
        event aggregate type. This enables instant message delivery to
        connected WebSocket clients across all API instances.
        
        Args:
            event: Outbox event to publish
        """
        try:
            redis_client = get_redis_client()
            
            # Determine Redis channel based on aggregate type
            channel = None
            
            if event.aggregate_type == 'message':
                # Publish to conversation channel
                conversation_id = event.payload.get('conversation_id')
                if conversation_id:
                    channel = f"conversation:{conversation_id}"
                    
                    # Prepare WebSocket message
                    ws_message = {
                        'type': 'message.created',
                        'message_id': str(event.aggregate_id),
                        'conversation_id': conversation_id,
                        'sender_id': event.payload.get('sender_id'),
                        'sender_username': event.payload.get('sender_username'),
                        'payload': event.payload.get('payload'),
                        'channels': event.payload.get('channels'),
                        'created_at': event.payload.get('created_at'),
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    
                    # Publish to Redis channel
                    redis_client.publish(channel, json.dumps(ws_message))
                    
                    logger.debug(
                        f"Published event {event.id} to Redis channel {channel}"
                    )
            
            elif event.aggregate_type == 'conversation':
                # Publish to conversation channel
                conversation_id = event.aggregate_id
                channel = f"conversation:{conversation_id}"
                
                # Prepare WebSocket message based on event type
                if event.event_type == 'conversation.read':
                    ws_message = {
                        'type': 'conversation.read',
                        'conversation_id': conversation_id,
                        'user_id': event.payload.get('user_id'),
                        'username': event.payload.get('username'),
                        'message_count': event.payload.get('message_count'),
                        'read_at': event.payload.get('read_at'),
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    
                    redis_client.publish(channel, json.dumps(ws_message))
                    logger.debug(f"Published to Redis channel {channel}")
            
        except Exception as e:
            # Don't fail the entire outbox publishing if Redis fails
            # Log error and continue (WebSocket notifications are best-effort)
            logger.error(
                f"Failed to publish event {event.id} to Redis: {e}. "
                f"Continuing with Kafka publishing."
            )
    
    def _publish_event_to_kafka(self, event: OutboxEvent, db: Session) -> bool:
        """
        Publish single event to Kafka.
        
        Args:
            event: Outbox event to publish
            db: Database session for updating event status
            
        Returns:
            True if published successfully, False otherwise
        """
        try:
            topic = self._determine_kafka_topic(event.event_type)
            partition_key = self._get_partition_key(event)
            
            # Prepare Kafka message
            kafka_message = {
                'event_id': str(event.id),
                'aggregate_type': event.aggregate_type,
                'aggregate_id': str(event.aggregate_id),
                'event_type': event.event_type,
                'payload': event.payload,
                'created_at': event.created_at.isoformat(),
                'published_at': datetime.utcnow().isoformat()
            }
            
            # Publish to Kafka (synchronous send for reliability)
            future = self.producer.send(
                topic=topic,
                key=partition_key,
                value=kafka_message
            )
            
            # Block until message is sent or timeout
            record_metadata = future.get(timeout=10)
            
            logger.debug(
                f"Published event {event.id} to Kafka topic {topic} "
                f"partition {record_metadata.partition} offset {record_metadata.offset}"
            )
            
            # Mark as published in database
            repository = Repository(db)
            repository.mark_outbox_event_published(event.id)
            
            # Publish to Redis Pub/Sub for real-time WebSocket notifications
            self._publish_event_to_redis(event)
            
            # Update metrics
            outbox_published_total.inc()
            
            self.events_published += 1
            return True
            
        except KafkaError as e:
            logger.error(f"Kafka error publishing event {event.id}: {e}")
            
            # Handle retries with exponential backoff
            if event.version < MAX_RETRIES:
                backoff_delay = INITIAL_BACKOFF_SECONDS * (2 ** (event.version - 1))
                logger.info(
                    f"Event {event.id} failed (attempt {event.version}/{MAX_RETRIES}), "
                    f"will retry after {backoff_delay}s"
                )
                
                # Update version and error message
                repository = Repository(db)
                repository.mark_outbox_event_failed(event.id, str(e))
                
                # Sleep before next retry
                time.sleep(backoff_delay)
            else:
                logger.error(
                    f"Event {event.id} failed after {MAX_RETRIES} attempts, "
                    f"publishing to Dead Letter Queue"
                )
                # Publish to DLQ topic
                self._publish_to_dlq(event, str(e))
                
                # Update metrics
                outbox_failed_total.labels(
                    aggregate_type=event.aggregate_type,
                    event_type=event.event_type
                ).inc()
                dlq_messages_total.labels(
                    reason="max_retries_exceeded",
                    aggregate_type=event.aggregate_type
                ).inc()
                
                self.events_failed += 1
            
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error publishing event {event.id}: {e}")
            
            # Update error message
            repository = Repository(db)
            repository.mark_outbox_event_failed(event.id, str(e))
            
            return False
    
    def _poll_and_publish(self):
        """
        Poll unpublished events and publish to Kafka.
        
        This is the main polling loop executed every POLL_INTERVAL_SECONDS.
        """
        db = self.SessionLocal()
        try:
            # Fetch unpublished events
            repository = Repository(db)
            events = repository.get_unpublished_outbox_events(limit=BATCH_SIZE)
            
            if events:
                logger.info(f"Found {len(events)} unpublished events")
                
                # Update pending events gauge
                outbox_pending_events.set(len(events))
                
                # Publish each event
                published_count = 0
                for event in events:
                    # Time the publish operation
                    start_time = time.time()
                    if self._publish_event_to_kafka(event, db):
                        published_count += 1
                    duration = time.time() - start_time
                    outbox_publish_duration_seconds.observe(duration)
                
                logger.info(
                    f"Published {published_count}/{len(events)} events successfully"
                )
            else:
                # No pending events
                outbox_pending_events.set(0)
            
            self.last_poll_time = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error in polling loop: {e}")
            db.rollback()
        finally:
            db.close()
    
    def run(self):
        """
        Run the outbox poller continuously.
        
        Polls the database every POLL_INTERVAL_SECONDS for unpublished events
        and publishes them to Kafka. Runs until interrupted (Ctrl+C).
        """
        logger.info("Starting Outbox Poller...")
        logger.info(f"Poll interval: {POLL_INTERVAL_SECONDS}s")
        logger.info(f"Batch size: {BATCH_SIZE}")
        logger.info(f"Max retries: {MAX_RETRIES}")
        
        try:
            while True:
                start_time = time.time()
                
                # Execute poll and publish
                self._poll_and_publish()
                
                # Calculate sleep time to maintain consistent interval
                elapsed = time.time() - start_time
                sleep_time = max(0, POLL_INTERVAL_SECONDS - elapsed)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    logger.warning(
                        f"Polling took {elapsed:.2f}s, longer than interval {POLL_INTERVAL_SECONDS}s"
                    )
                
        except KeyboardInterrupt:
            logger.info("Shutting down Outbox Poller (Ctrl+C received)...")
            self._shutdown()
        except Exception as e:
            logger.error(f"Fatal error in Outbox Poller: {e}")
            self._shutdown()
            sys.exit(1)
    
    def _shutdown(self):
        """Gracefully shutdown poller and close connections."""
        logger.info("Closing Kafka producer...")
        if self.producer:
            self.producer.flush()
            self.producer.close()
        
        logger.info("Closing database connections...")
        self.engine.dispose()
        
        logger.info(
            f"Outbox Poller shutdown complete. "
            f"Total published: {self.events_published}, Failed: {self.events_failed}"
        )


def main():
    """Main entry point for outbox poller worker."""
    poller = OutboxPoller()
    poller.run()


if __name__ == "__main__":
    main()
