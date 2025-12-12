"""
Upload Garbage Collector Worker.

Scheduled job that cleans up abandoned file uploads (status=UPLOADING or PENDING
for more than 24 hours). Deletes chunk records, removes chunk objects from MinIO,
and marks the file as FAILED.

Should be run as a daily cron job (e.g., at 2 AM).
"""
import logging
import sys
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from db.database import SessionLocal
from db.models import File, FileChunkModel, FileStatus
from services.minio_client import get_minio_client
from workers.metrics import (
    UPLOADS_CLEANED_TOTAL,
    CLEANUP_DURATION_SECONDS
)
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UploadGarbageCollector:
    """Garbage collector for abandoned file uploads."""
    
    def __init__(self):
        """Initialize garbage collector."""
        self.minio_client = get_minio_client()
        logger.info("UploadGarbageCollector initialized")
    
    def find_abandoned_uploads(self, db: Session, expiration_hours: int = 24) -> list[File]:
        """
        Find abandoned file uploads.
        
        Args:
            db: Database session
            expiration_hours: Hours after which upload is considered abandoned (default: 24)
            
        Returns:
            List of abandoned File records
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=expiration_hours)
        
        abandoned_files = db.query(File).filter(
            and_(
                File.status.in_([FileStatus.PENDING, FileStatus.UPLOADING]),
                File.created_at < cutoff_time
            )
        ).all()
        
        logger.info(f"Found {len(abandoned_files)} abandoned uploads older than {expiration_hours}h")
        
        return abandoned_files
    
    def cleanup_upload(self, db: Session, file: File) -> bool:
        """
        Clean up a single abandoned upload.
        
        Args:
            db: Database session
            file: File record to clean up
            
        Returns:
            True if cleanup successful, False otherwise
        """
        upload_id = file.id
        logger.info(
            f"Cleaning up abandoned upload: {upload_id} "
            f"(created {file.created_at}, {file.uploaded_chunks}/{file.total_chunks} chunks)"
        )
        
        try:
            # Get all chunk records
            chunks = db.query(FileChunkModel).filter(
                FileChunkModel.file_id == upload_id
            ).all()
            
            chunk_count = len(chunks)
            logger.info(f"Found {chunk_count} chunk records for {upload_id}")
            
            # Delete chunk objects from MinIO
            deleted_objects = 0
            for chunk in chunks:
                try:
                    if self.minio_client.object_exists(chunk.storage_key):
                        self.minio_client.remove_object(chunk.storage_key)
                        deleted_objects += 1
                except Exception as e:
                    logger.warning(f"Failed to delete chunk {chunk.storage_key}: {e}")
            
            logger.info(f"Deleted {deleted_objects}/{chunk_count} chunk objects from MinIO")
            
            # Delete chunk records from database
            deleted_records = db.query(FileChunkModel).filter(
                FileChunkModel.file_id == upload_id
            ).delete()
            
            logger.info(f"Deleted {deleted_records} chunk records from database")
            
            # Update file status to FAILED
            file.status = FileStatus.FAILED
            db.commit()
            
            logger.info(f"Marked upload {upload_id} as FAILED")
            
            # Update metrics
            UPLOADS_CLEANED_TOTAL.inc()
            
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up upload {upload_id}: {e}")
            db.rollback()
            return False
    
    def run_cleanup(self, expiration_hours: int = 24) -> dict:
        """
        Run garbage collection for abandoned uploads.
        
        Args:
            expiration_hours: Hours after which upload is considered abandoned (default: 24)
            
        Returns:
            Cleanup statistics (total, cleaned, failed)
        """
        start_time = time.time()
        
        logger.info(f"Starting upload garbage collection (expiration: {expiration_hours}h)")
        
        db: Session = SessionLocal()
        
        stats = {
            'total': 0,
            'cleaned': 0,
            'failed': 0
        }
        
        try:
            # Find abandoned uploads
            abandoned_files = self.find_abandoned_uploads(db, expiration_hours)
            stats['total'] = len(abandoned_files)
            
            if stats['total'] == 0:
                logger.info("No abandoned uploads found")
                return stats
            
            # Clean up each upload
            for file in abandoned_files:
                success = self.cleanup_upload(db, file)
                
                if success:
                    stats['cleaned'] += 1
                else:
                    stats['failed'] += 1
            
            # Record cleanup duration
            duration = time.time() - start_time
            CLEANUP_DURATION_SECONDS.observe(duration)
            
            logger.info(
                f"Garbage collection completed in {duration:.2f}s: "
                f"{stats['cleaned']}/{stats['total']} uploads cleaned, "
                f"{stats['failed']} failed"
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Garbage collection failed: {e}")
            raise
        finally:
            db.close()


def main():
    """Entry point for garbage collector worker."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Upload garbage collector')
    parser.add_argument(
        '--expiration-hours',
        type=int,
        default=24,
        help='Hours after which upload is considered abandoned (default: 24)'
    )
    
    args = parser.parse_args()
    
    collector = UploadGarbageCollector()
    
    try:
        stats = collector.run_cleanup(expiration_hours=args.expiration_hours)
        
        print(f"\n✓ Garbage collection completed")
        print(f"  Total abandoned uploads: {stats['total']}")
        print(f"  Successfully cleaned: {stats['cleaned']}")
        print(f"  Failed to clean: {stats['failed']}")
        
        sys.exit(0)
        
    except Exception as e:
        print(f"\n✗ Garbage collection failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
