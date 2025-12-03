"""
MinIO client for object storage operations.
Provides methods for presigned URLs, file upload/download, and object management.
"""
import logging
from datetime import timedelta
from typing import Optional
from minio import Minio
from minio.error import S3Error
from core.config import settings

logger = logging.getLogger(__name__)


class MinIOClient:
    """Client for MinIO object storage operations."""
    
    def __init__(self):
        """Initialize MinIO client."""
        try:
            self.client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
            
            # Ensure bucket exists
            if not self.client.bucket_exists(settings.minio_bucket):
                self.client.make_bucket(settings.minio_bucket)
                logger.info(f"Created MinIO bucket: {settings.minio_bucket}")
            else:
                logger.info(f"MinIO bucket exists: {settings.minio_bucket}")
                
        except S3Error as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
            raise
    
    def presigned_put_url(self, object_name: str, expires: timedelta = timedelta(hours=1)) -> str:
        """
        Generate a presigned PUT URL for uploading a file.
        
        Args:
            object_name: Name/path of the object in MinIO
            expires: URL expiration time (default: 1 hour)
            
        Returns:
            Presigned URL string
        """
        try:
            url = self.client.presigned_put_object(
                settings.minio_bucket,
                object_name,
                expires=expires
            )
            logger.info(f"Generated presigned PUT URL for: {object_name}")
            return url
        except S3Error as e:
            logger.error(f"Failed to generate presigned PUT URL: {e}")
            raise
    
    def presigned_get_url(self, object_name: str, expires: timedelta = timedelta(hours=1)) -> str:
        """
        Generate a presigned GET URL for downloading a file.
        
        Args:
            object_name: Name/path of the object in MinIO
            expires: URL expiration time (default: 1 hour)
            
        Returns:
            Presigned URL string
        """
        try:
            url = self.client.presigned_get_object(
                settings.minio_bucket,
                object_name,
                expires=expires
            )
            logger.info(f"Generated presigned GET URL for: {object_name}")
            return url
        except S3Error as e:
            logger.error(f"Failed to generate presigned GET URL: {e}")
            raise
    
    def stat_object(self, object_name: str) -> Optional[dict]:
        """
        Get metadata about an object.
        
        Args:
            object_name: Name/path of the object in MinIO
            
        Returns:
            Dictionary with object metadata (size, etag, content_type) or None if not found
        """
        try:
            stat = self.client.stat_object(settings.minio_bucket, object_name)
            return {
                "size": stat.size,
                "etag": stat.etag,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified
            }
        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning(f"Object not found: {object_name}")
                return None
            logger.error(f"Failed to stat object: {e}")
            raise
    
    def remove_object(self, object_name: str) -> bool:
        """
        Remove an object from MinIO.
        
        Args:
            object_name: Name/path of the object in MinIO
            
        Returns:
            True if object was removed successfully, False otherwise
        """
        try:
            self.client.remove_object(settings.minio_bucket, object_name)
            logger.info(f"Removed object: {object_name}")
            return True
        except S3Error as e:
            logger.error(f"Failed to remove object: {e}")
            return False
    
    def object_exists(self, object_name: str) -> bool:
        """
        Check if an object exists in MinIO.
        
        Args:
            object_name: Name/path of the object in MinIO
            
        Returns:
            True if object exists, False otherwise
        """
        return self.stat_object(object_name) is not None
    
    def put_object(self, object_name: str, data, length: int, content_type: str = "application/octet-stream"):
        """
        Upload an object to MinIO.
        
        Args:
            object_name: Name/path of the object in MinIO
            data: File-like object or bytes to upload
            length: Size of the data in bytes
            content_type: MIME type of the object
            
        Returns:
            True if upload successful
        """
        try:
            self.client.put_object(
                settings.minio_bucket,
                object_name,
                data,
                length,
                content_type=content_type
            )
            logger.info(f"Uploaded object: {object_name} ({length} bytes)")
            return True
        except S3Error as e:
            logger.error(f"Failed to upload object: {e}")
            raise
    
    def compose_objects(self, destination_object: str, source_objects: list[str]) -> bool:
        """
        Compose multiple objects into a single object using MinIO server-side merge.
        
        This performs a server-side copy and concatenation of multiple objects
        without downloading/uploading data, which is much more efficient for large files.
        
        Args:
            destination_object: Name/path of the destination object
            source_objects: List of source object names to merge (in order)
            
        Returns:
            True if composition successful
            
        Raises:
            S3Error: If any source object doesn't exist or composition fails
        """
        try:
            from minio.commonconfig import ComposeSource
            
            # Create ComposeSource objects for each chunk
            sources = [
                ComposeSource(settings.minio_bucket, obj)
                for obj in source_objects
            ]
            
            # Compose objects into destination
            self.client.compose_object(
                settings.minio_bucket,
                destination_object,
                sources
            )
            
            logger.info(
                f"Composed {len(source_objects)} objects into {destination_object}"
            )
            return True
            
        except S3Error as e:
            logger.error(f"Failed to compose objects: {e}")
            raise
    
    def list_objects(self, prefix: str) -> list[str]:
        """
        List objects with a given prefix.
        
        Args:
            prefix: Object name prefix to filter by
            
        Returns:
            List of object names matching the prefix
        """
        try:
            objects = self.client.list_objects(
                settings.minio_bucket,
                prefix=prefix,
                recursive=True
            )
            object_names = [obj.object_name for obj in objects]
            logger.info(f"Found {len(object_names)} objects with prefix: {prefix}")
            return object_names
        except S3Error as e:
            logger.error(f"Failed to list objects: {e}")
            raise


# Global MinIO client instance (initialized on first use)
_minio_client: MinIOClient = None


def get_minio_client() -> MinIOClient:
    """
    Get or create global MinIO client instance.
    
    Returns:
        MinIOClient instance
    """
    global _minio_client
    if _minio_client is None:
        _minio_client = MinIOClient()
    return _minio_client
