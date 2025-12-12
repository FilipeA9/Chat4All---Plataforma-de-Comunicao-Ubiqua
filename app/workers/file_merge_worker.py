"""
File Merge Worker for resumable chunked file uploads.

Consumes file_merge_request events from Kafka, retrieves all chunks from MinIO,
merges them into a single file using MinIO server-side compose, updates file status,
and cleans up chunk records and objects.
"""
import logging
import json
import sys
from datetime import datetime
from uuid import UUID
from typing import List
from kafka import KafkaConsumer
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import File, FileChunkModel, FileStatus
from services.minio_client import get_minio_client
from services.kafka_producer import get_kafka_producer
from core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FileMergeWorker:
    """Worker for merging file chunks into complete files."""
    
    def __init__(self):
        """Initialize file merge worker."""
        self.minio_client = get_minio_client()
        self.kafka_producer = get_kafka_producer()
        
        # Initialize Kafka consumer for file_merge_requests topic
        self.consumer = KafkaConsumer(
            'file_merge_requests',
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id='file-merge-worker-group',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            max_poll_records=10  # Process 10 merge requests at a time
        )
        
        logger.info("FileMergeWorker initialized successfully")
    
    def process_merge_request(self, event: dict):
        """
        Process a single file merge request.
        
        Args:
            event: Merge request event with upload_id, filename, total_chunks, storage_key
        """
        upload_id = event.get('upload_id')
        logger.info(f"Processing merge request for upload_id={upload_id}")
        
        db: Session = SessionLocal()
        
        try:
            # Get file record
            file = db.query(File).filter(File.id == UUID(upload_id)).first()
            if not file:
                logger.error(f"File not found for upload_id={upload_id}")
                return
            
            # Get all chunks ordered by chunk_number
            chunks = db.query(FileChunkModel).filter(
                FileChunkModel.file_id == UUID(upload_id)
            ).order_by(FileChunkModel.chunk_number).all()
            
            if len(chunks) != file.total_chunks:
                logger.error(
                    f"Chunk count mismatch for upload_id={upload_id}: "
                    f"expected {file.total_chunks}, got {len(chunks)}"
                )
                file.status = FileStatus.FAILED
                db.commit()
                return
            
            # Extract chunk storage keys in order
            chunk_storage_keys = [chunk.storage_key for chunk in chunks]
            
            logger.info(
                f"Merging {len(chunk_storage_keys)} chunks for upload_id={upload_id}"
            )
            
            # Compose chunks into final file using MinIO server-side merge
            destination_key = file.storage_key or event.get('storage_key')
            self.minio_client.compose_objects(
                destination_object=destination_key,
                source_objects=chunk_storage_keys
            )
            
            logger.info(f"Successfully composed file: {destination_key}")
            
            # Update file status to COMPLETED
            file.status = FileStatus.COMPLETED
            file.completed_at = datetime.utcnow()
            file.storage_key = destination_key
            db.commit()
            
            # Cleanup: Delete chunk records from database
            deleted_chunks = db.query(FileChunkModel).filter(
                FileChunkModel.file_id == UUID(upload_id)
            ).delete()
            db.commit()
            
            logger.info(f"Deleted {deleted_chunks} chunk records for upload_id={upload_id}")
            
            # Cleanup: Delete chunk objects from MinIO
            for chunk_key in chunk_storage_keys:
                try:
                    self.minio_client.remove_object(chunk_key)
                except Exception as e:
                    logger.warning(f"Failed to delete chunk {chunk_key}: {e}")
            
            logger.info(f"Deleted {len(chunk_storage_keys)} chunk objects from MinIO")
            
            # Publish FileUploadCompleted event
            completion_event = {
                "upload_id": upload_id,
                "file_id": str(file.id),
                "conversation_id": file.conversation_id,
                "uploader_id": file.uploader_id,
                "filename": file.filename,
                "file_size": file.file_size,
                "mime_type": file.mime_type,
                "storage_key": destination_key,
                "completed_at": file.completed_at.isoformat(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.kafka_producer.publish_message(
                topic='file_upload_completed',
                message=completion_event,
                partition_key=upload_id
            )
            
            logger.info(
                f"File merge completed successfully: upload_id={upload_id}, "
                f"file={destination_key}, size={file.file_size} bytes"
            )
            
        except Exception as e:
            logger.error(f"Error processing merge request for upload_id={upload_id}: {e}")
            
            # Update file status to FAILED
            try:
                file = db.query(File).filter(File.id == UUID(upload_id)).first()
                if file:
                    file.status = FileStatus.FAILED
                    db.commit()
            except Exception as update_error:
                logger.error(f"Failed to update file status: {update_error}")
            
        finally:
            db.close()
    
    def run(self):
        """
        Run the file merge worker (infinite loop).
        
        Consumes file_merge_request events from Kafka and processes them.
        """
        logger.info("Starting FileMergeWorker...")
        
        try:
            for message in self.consumer:
                event = message.value
                logger.info(f"Received merge request: {event}")
                
                try:
                    self.process_merge_request(event)
                except Exception as e:
                    logger.error(f"Failed to process merge request: {e}")
                    # Continue processing next message
                    
        except KeyboardInterrupt:
            logger.info("Shutting down FileMergeWorker...")
        finally:
            self.consumer.close()
            logger.info("FileMergeWorker stopped")


def main():
    """Entry point for file merge worker."""
    worker = FileMergeWorker()
    worker.run()


if __name__ == "__main__":
    main()
