"""
Instagram Mock Worker
Consumes messages from 'instagram_outgoing' topic and simulates sending
to Instagram by logging and updating message status.
"""
import json
import logging
import signal
import sys
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.repository import Repository
from db.models import MessageStatus
from uuid import UUID
from core.config import settings

logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


def process_message(message_data: dict, db: Session) -> None:
    """
    Process message by logging and updating status in database.
    
    Args:
        message_data: Message data from Kafka
        db: Database session
    """
    message_id = message_data.get("message_id")
    sender_id = message_data.get("sender_id")
    
    # Log message sending
    logger.info(f"INFO: Mensagem {message_id} enviada para o usuário {sender_id} no Instagram")
    
    # Update message status in database
    repository = Repository(db)
    try:
        repository.update_message_status(
            UUID(message_id),
            MessageStatus.DELIVERED,
            channel="instagram",
            details={"delivered_at": "now"}
        )
        logger.info(f"Message {message_id} status updated to DELIVERED")
    except Exception as e:
        logger.error(f"Failed to update message status: {e}")


def main():
    """Main worker loop."""
    global shutdown_requested
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Instagram Mock Worker starting...")
    
    try:
        # Create Kafka consumer
        consumer = KafkaConsumer(
            "instagram_outgoing",
            bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id="instagram_mock_group",
            auto_offset_reset='earliest',
            enable_auto_commit=True
        )
        
        logger.info("Instagram Mock Worker connected to Kafka")
        
        # Process messages
        for message in consumer:
            if shutdown_requested:
                logger.info("Shutdown requested, stopping message processing")
                break
            
            try:
                message_data = message.value
                db = SessionLocal()
                process_message(message_data, db)
                db.close()
            except Exception as e:
                logger.error(f"Error processing message: {e}")
        
        # Clean up
        consumer.close()
        logger.info("Instagram Mock Worker stopped gracefully")
        
    except KafkaError as e:
        logger.error(f"Kafka error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
