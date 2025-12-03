"""
Example Python client for resumable chunked file uploads.

Demonstrates:
- Initiating upload session
- Uploading chunks with retry logic and exponential backoff
- Resuming interrupted uploads by querying status and uploading missing chunks
- Completing the upload

Usage:
    python examples/chunked_upload_client.py --file path/to/video.mp4 --conversation-id 123
"""
import argparse
import hashlib
import math
import os
import sys
import time
from typing import Optional
import requests


class ChunkedUploadClient:
    """Client for resumable chunked file uploads."""
    
    def __init__(self, api_url: str, access_token: str):
        """
        Initialize upload client.
        
        Args:
            api_url: Base URL of the API (e.g., http://localhost:8000)
            access_token: JWT access token for authentication
        """
        self.api_url = api_url.rstrip('/')
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
    
    def initiate_upload(
        self,
        conversation_id: int,
        file_path: str,
        chunk_size: int = 10 * 1024 * 1024  # 10MB default
    ) -> dict:
        """
        Initiate a chunked file upload session.
        
        Args:
            conversation_id: ID of conversation where file will be shared
            file_path: Path to local file
            chunk_size: Size of each chunk in bytes (1MB-50MB)
            
        Returns:
            Upload session metadata (upload_id, total_chunks, chunk_size)
        """
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        
        # Detect MIME type
        mime_type = self._detect_mime_type(filename)
        
        payload = {
            'conversation_id': conversation_id,
            'filename': filename,
            'file_size': file_size,
            'mime_type': mime_type,
            'chunk_size': chunk_size
        }
        
        response = requests.post(
            f'{self.api_url}/v1/files/initiate',
            headers=self.headers,
            json=payload
        )
        
        response.raise_for_status()
        return response.json()
    
    def upload_chunk(
        self,
        upload_id: str,
        chunk_number: int,
        chunk_data: bytes,
        max_retries: int = 5
    ) -> dict:
        """
        Upload a single chunk with exponential backoff retry logic.
        
        Args:
            upload_id: Upload session UUID
            chunk_number: 1-based chunk number
            chunk_data: Binary chunk data
            max_retries: Maximum retry attempts (default: 5)
            
        Returns:
            Upload progress (chunk_number, uploaded_chunks, percentage)
        """
        retry_count = 0
        backoff_seconds = 1
        
        while retry_count <= max_retries:
            try:
                # Calculate SHA-256 checksum for integrity
                checksum = hashlib.sha256(chunk_data).hexdigest()
                
                headers = {
                    'Authorization': self.headers['Authorization'],
                    'Content-Type': 'application/octet-stream'
                }
                
                response = requests.post(
                    f'{self.api_url}/v1/files/{upload_id}/chunks',
                    headers=headers,
                    params={
                        'chunk_number': chunk_number,
                        'checksum_sha256': checksum
                    },
                    data=chunk_data
                )
                
                # Handle 409 Conflict (duplicate chunk) - already uploaded
                if response.status_code == 409:
                    print(f"  Chunk {chunk_number} already uploaded, skipping")
                    return {'chunk_number': chunk_number, 'skipped': True}
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                retry_count += 1
                
                if retry_count > max_retries:
                    print(f"  Failed to upload chunk {chunk_number} after {max_retries} retries: {e}")
                    raise
                
                print(f"  Retry {retry_count}/{max_retries} for chunk {chunk_number} in {backoff_seconds}s...")
                time.sleep(backoff_seconds)
                
                # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                backoff_seconds = min(backoff_seconds * 2, 60)
    
    def get_upload_status(self, upload_id: str) -> dict:
        """
        Query upload session status.
        
        Args:
            upload_id: Upload session UUID
            
        Returns:
            Upload status (uploaded_chunks, total_chunks, missing_chunks)
        """
        response = requests.get(
            f'{self.api_url}/v1/files/{upload_id}/status',
            headers=self.headers
        )
        
        response.raise_for_status()
        return response.json()
    
    def complete_upload(self, upload_id: str) -> dict:
        """
        Complete the upload and trigger chunk merge.
        
        Args:
            upload_id: Upload session UUID
            
        Returns:
            Completion status (status=merging, estimated_completion)
        """
        response = requests.post(
            f'{self.api_url}/v1/files/{upload_id}/complete',
            headers=self.headers
        )
        
        response.raise_for_status()
        return response.json()
    
    def upload_file(
        self,
        conversation_id: int,
        file_path: str,
        chunk_size: int = 10 * 1024 * 1024,
        resume_upload_id: Optional[str] = None
    ) -> dict:
        """
        Upload a file with automatic resumption support.
        
        Args:
            conversation_id: ID of conversation where file will be shared
            file_path: Path to local file
            chunk_size: Size of each chunk in bytes (default: 10MB)
            resume_upload_id: Optional upload_id to resume interrupted upload
            
        Returns:
            Completion response with upload_id and status
        """
        if resume_upload_id:
            # Resume interrupted upload
            print(f"Resuming upload: {resume_upload_id}")
            status = self.get_upload_status(resume_upload_id)
            upload_id = resume_upload_id
            total_chunks = status['total_chunks']
            missing_chunks = status.get('missing_chunks', [])
            
            print(f"Upload status: {status['uploaded_chunks']}/{total_chunks} chunks uploaded")
            print(f"Missing chunks: {len(missing_chunks)}")
            
            # Upload only missing chunks
            chunks_to_upload = missing_chunks
            
        else:
            # Start new upload
            print(f"Initiating upload: {file_path}")
            session = self.initiate_upload(conversation_id, file_path, chunk_size)
            upload_id = session['upload_id']
            total_chunks = session['total_chunks']
            
            print(f"Upload initiated: upload_id={upload_id}, {total_chunks} chunks")
            
            # Upload all chunks
            chunks_to_upload = list(range(1, total_chunks + 1))
        
        # Upload chunks
        file_size = os.path.getsize(file_path)
        
        with open(file_path, 'rb') as f:
            for chunk_number in chunks_to_upload:
                # Calculate chunk offset and size
                offset = (chunk_number - 1) * chunk_size
                f.seek(offset)
                chunk_data = f.read(chunk_size)
                
                if not chunk_data:
                    print(f"Warning: Chunk {chunk_number} is empty, skipping")
                    continue
                
                print(f"Uploading chunk {chunk_number}/{total_chunks} ({len(chunk_data)} bytes)...")
                
                try:
                    result = self.upload_chunk(upload_id, chunk_number, chunk_data)
                    
                    if result.get('skipped'):
                        continue
                    
                    percentage = result.get('percentage', 0)
                    print(f"  Progress: {percentage:.2f}%")
                    
                except Exception as e:
                    print(f"Failed to upload chunk {chunk_number}: {e}")
                    print(f"To resume: python {sys.argv[0]} --resume {upload_id} --file {file_path}")
                    sys.exit(1)
        
        # Complete upload
        print("All chunks uploaded, triggering merge...")
        completion = self.complete_upload(upload_id)
        
        print(f"Upload complete! Status: {completion['status']}")
        print(f"Estimated completion: {completion.get('estimated_completion')}")
        
        return completion
    
    @staticmethod
    def _detect_mime_type(filename: str) -> str:
        """Detect MIME type from file extension."""
        ext = os.path.splitext(filename)[1].lower()
        mime_types = {
            '.mp4': 'video/mp4',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.mkv': 'video/x-matroska',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.pdf': 'application/pdf',
            '.txt': 'text/plain',
            '.zip': 'application/zip'
        }
        return mime_types.get(ext, 'application/octet-stream')


def main():
    """Command-line interface for chunked upload client."""
    parser = argparse.ArgumentParser(description='Resumable chunked file upload client')
    parser.add_argument('--file', required=True, help='Path to file to upload')
    parser.add_argument('--conversation-id', type=int, help='Conversation ID (required for new uploads)')
    parser.add_argument('--resume', help='Upload ID to resume (optional)')
    parser.add_argument('--api-url', default='http://localhost:8000', help='API base URL')
    parser.add_argument('--token', required=True, help='JWT access token')
    parser.add_argument('--chunk-size', type=int, default=10*1024*1024, help='Chunk size in bytes (default: 10MB)')
    
    args = parser.parse_args()
    
    if not args.resume and not args.conversation_id:
        parser.error('--conversation-id is required for new uploads')
    
    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}")
        sys.exit(1)
    
    # Create client
    client = ChunkedUploadClient(args.api_url, args.token)
    
    # Upload file
    try:
        result = client.upload_file(
            conversation_id=args.conversation_id,
            file_path=args.file,
            chunk_size=args.chunk_size,
            resume_upload_id=args.resume
        )
        
        print("\n✓ Upload successful!")
        print(f"  Upload ID: {result['upload_id']}")
        print(f"  Status: {result['status']}")
        
    except Exception as e:
        print(f"\n✗ Upload failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
