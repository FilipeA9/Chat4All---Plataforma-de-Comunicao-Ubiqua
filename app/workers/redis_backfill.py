"""
Redis Fallback Queue Worker (T061)

This worker polls the Redis fallback queue (fallback:message_queue) every 10 seconds
and attempts to publish messages to Kafka when the circuit breaker recovers.

When Kafka is unavailable (circuit open), messages are queued in Redis by the API.
This worker continuously attempts to drain the queue by publishing to Kafka.

Features:
- Polls Redis queue every 10 seconds
- Respects circuit breaker state (only publishes when circuit closed/half-open)
- Atomic LPOP operations to prevent duplicate processing
- Handles batch processing for efficiency
- Logs progress and errors

Usage:
    python -m workers.redis_backfill
"""
import os
import sys
import logging
import json
import time
import pybreaker
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.redis_client import get_redis_client
from services.kafka_producer import get_kafka_producer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration
FALLBACK_QUEUE_KEY = "fallback:message_queue"
POLL_INTERVAL_SECONDS = 10
BATCH_SIZE = 50  # Process up to 50 messages per batch


def poll_fallback_queue():
    """
    Poll Redis fallback queue and attempt to publish messages to Kafka.
    
    This function continuously polls the fallback queue and attempts to
    publish messages to Kafka. If the circuit breaker is open, it waits
    for the next poll interval.
    """
    logger.info("Redis backfill worker started")
    logger.info(f"Polling {FALLBACK_QUEUE_KEY} every {POLL_INTERVAL_SECONDS} seconds")
    
    redis_client = get_redis_client()
    kafka_producer = get_kafka_producer()
    
    messages_processed = 0
    messages_failed = 0
    
    while True:
        try:
            # Check queue length
            queue_length = redis_client.llen(FALLBACK_QUEUE_KEY)
            
            if queue_length == 0:
                logger.debug("Fallback queue is empty, waiting...")
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            
            logger.info(f"Found {queue_length} messages in fallback queue, processing batch...")
            
            # Process batch
            batch_count = 0
            for _ in range(min(BATCH_SIZE, queue_length)):
                # Atomic LPOP to get and remove message from queue
                message_json = redis_client.lpop(FALLBACK_QUEUE_KEY)
                
                if not message_json:
                    break
                
                try:
                    # Decode if bytes
                    if isinstance(message_json, bytes):
                        message_json = message_json.decode('utf-8')
                    
                    # Parse message payload
                    message_data = json.loads(message_json)
                    message_id = message_data.get("message_id")
                    
                    # Attempt to publish to Kafka
                    try:
                        success = kafka_producer.publish_message(
                            topic="message_processing",
                            message=message_data
                        )
                        
                        if success:
                            logger.info(f"Message {message_id} published to Kafka from fallback queue")
                            messages_processed += 1
                            batch_count += 1
                        else:
                            logger.error(f"Failed to publish message {message_id} to Kafka")
                            messages_failed += 1
                            
                            # Re-queue message at end of list (retry later)
                            redis_client.rpush(FALLBACK_QUEUE_KEY, message_json)
                            logger.warning(f"Message {message_id} re-queued for retry")
                    
                    except pybreaker.CircuitBreakerError:
                        # Circuit is open - Kafka still unavailable
                        logger.warning(f"Kafka circuit breaker open, re-queuing message {message_id}")
                        
                        # Put message back at end of queue
                        redis_client.rpush(FALLBACK_QUEUE_KEY, message_json)
                        
                        # Stop processing batch, wait for circuit to recover
                        logger.info("Kafka unavailable, waiting for circuit to recover...")
                        break
                
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in fallback queue: {e}")
                    messages_failed += 1
                    # Discard invalid message (don't re-queue)
                
                except Exception as e:
                    logger.error(f"Error processing fallback message: {e}")
                    messages_failed += 1
                    # Re-queue message for retry
                    redis_client.rpush(FALLBACK_QUEUE_KEY, message_json)
            
            if batch_count > 0:
                logger.info(
                    f"Batch complete: {batch_count} messages published "
                    f"(total: {messages_processed} processed, {messages_failed} failed)"
                )
        
        except pybreaker.CircuitBreakerError:
            logger.warning("Redis circuit breaker open, waiting for recovery...")
        
        except Exception as e:
            logger.error(f"Unexpected error in backfill worker: {e}")
        
        # Wait before next poll
        time.sleep(POLL_INTERVAL_SECONDS)


def get_queue_stats() -> dict:
    """
    Get current fallback queue statistics.
    
    Returns:
        dict: Queue statistics (length, oldest message timestamp)
    """
    try:
        redis_client = get_redis_client()
        queue_length = redis_client.llen(FALLBACK_QUEUE_KEY)
        
        # Peek at oldest message (without removing)
        oldest_message = None
        if queue_length > 0:
            message_json = redis_client.lindex(FALLBACK_QUEUE_KEY, 0)
            if message_json:
                if isinstance(message_json, bytes):
                    message_json = message_json.decode('utf-8')
                message_data = json.loads(message_json)
                oldest_message = message_data.get("created_at")
        
        return {
            "queue_length": queue_length,
            "oldest_message_timestamp": oldest_message
        }
    
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")
        return {
            "queue_length": -1,
            "oldest_message_timestamp": None
        }


if __name__ == "__main__":
    """
    Main entry point for Redis backfill worker.
    
    Usage:
        python -m workers.redis_backfill
    """
    logger.info("=" * 80)
    logger.info("Redis Fallback Queue Backfill Worker (T061)")
    logger.info("=" * 80)
    
    # Display initial queue stats
    stats = get_queue_stats()
    logger.info(f"Initial queue length: {stats['queue_length']}")
    if stats['oldest_message_timestamp']:
        logger.info(f"Oldest message: {stats['oldest_message_timestamp']}")
    
    try:
        poll_fallback_queue()
    except KeyboardInterrupt:
        logger.info("Backfill worker stopped by user (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal error in backfill worker: {e}")
        sys.exit(1)
