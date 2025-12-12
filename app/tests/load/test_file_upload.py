"""
Load Test: File Upload Performance

Tests chunked file upload performance with multiple concurrent uploads.
Target: 100 concurrent 1GB file uploads, <5s per 10MB chunk

Usage:
    # Run with web UI
    locust -f tests/load/test_file_upload.py --host=http://localhost:8000

    # Run headless (100 concurrent uploads)
    locust -f tests/load/test_file_upload.py --host=http://localhost:8000 \
           --users=100 --spawn-rate=10 --run-time=10m --headless

    # Run smaller test
    locust -f tests/load/test_file_upload.py --host=http://localhost:8000 \
           --users=10 --spawn-rate=2 --run-time=5m
"""
import json
import random
import time
from io import BytesIO
from locust import HttpUser, task, between, events
from datetime import datetime


class FileUploader(HttpUser):
    """
    Simulates a user uploading large files using chunked resumable uploads.
    
    Each user:
    1. Authenticates to get JWT token
    2. Initiates file upload (random size 100MB-1GB)
    3. Uploads chunks sequentially (10MB each)
    4. Completes upload
    5. Monitors merge status
    """
    
    wait_time = between(1, 3)  # Wait 1-3s between chunks
    
    def on_start(self):
        """
        Authenticate and initialize upload state.
        """
        # Authenticate
        user_id = random.randint(1, 10)
        auth_response = self.client.post(
            "/auth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": f"user{user_id}",
                "client_secret": "password123",
                "scope": "read write"
            },
            name="/auth/token"
        )
        
        if auth_response.status_code == 200:
            self.access_token = auth_response.json()["access_token"]
            self.user_id = user_id
            self.headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
        else:
            self.access_token = None
            self.headers = {}
            print(f"Authentication failed: {auth_response.status_code}")
            return
        
        # Upload state
        self.current_upload = None
        self.uploaded_chunks = 0
    
    @task(1)
    def upload_file_workflow(self):
        """
        Complete file upload workflow: initiate → upload chunks → complete
        """
        if not self.access_token:
            return
        
        # Step 1: Initiate upload
        if not self.current_upload:
            self.initiate_upload()
        
        # Step 2: Upload chunks
        elif self.uploaded_chunks < self.current_upload["total_chunks"]:
            self.upload_chunk()
        
        # Step 3: Complete upload
        elif self.uploaded_chunks == self.current_upload["total_chunks"]:
            self.complete_upload()
        
        # Step 4: Check status (optional)
        else:
            self.check_status()
    
    def initiate_upload(self):
        """
        Initiate a new chunked file upload.
        """
        # Random file size: 100MB to 1GB
        file_size = random.randint(100 * 1024 * 1024, 1024 * 1024 * 1024)
        chunk_size = 10 * 1024 * 1024  # 10MB chunks
        
        conversation_id = random.randint(1, 50)
        
        payload = {
            "conversation_id": conversation_id,
            "filename": f"load_test_file_{int(time.time())}.bin",
            "file_size": file_size,
            "mime_type": "application/octet-stream",
            "checksum_sha256": "a" * 64,  # Dummy checksum
            "chunk_size": chunk_size
        }
        
        with self.client.post(
            "/v1/files/initiate",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="/v1/files/initiate"
        ) as response:
            if response.status_code == 201:
                data = response.json()
                self.current_upload = {
                    "upload_id": data["upload_id"],
                    "total_chunks": data["total_chunks"],
                    "chunk_size": data["chunk_size"],
                    "file_size": file_size
                }
                self.uploaded_chunks = 0
                response.success()
            else:
                response.failure(f"Initiate failed: {response.status_code}")
    
    def upload_chunk(self):
        """
        Upload a single file chunk.
        """
        if not self.current_upload:
            return
        
        chunk_number = self.uploaded_chunks + 1
        upload_id = self.current_upload["upload_id"]
        chunk_size = self.current_upload["chunk_size"]
        
        # Generate dummy chunk data
        # Last chunk may be smaller
        if chunk_number == self.current_upload["total_chunks"]:
            remaining = self.current_upload["file_size"] % chunk_size
            if remaining > 0:
                chunk_size = remaining
        
        chunk_data = b"X" * chunk_size
        
        with self.client.post(
            f"/v1/files/{upload_id}/chunks",
            params={"chunk_number": chunk_number},
            data=chunk_data,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/octet-stream"
            },
            catch_response=True,
            name="/v1/files/{id}/chunks"
        ) as response:
            if response.status_code == 200:
                self.uploaded_chunks += 1
                
                # Check if chunk upload met target (<5s for 10MB)
                response_time_ms = response.elapsed.total_seconds() * 1000
                if response_time_ms < 5000:
                    response.success()
                else:
                    response.failure(f"Chunk upload too slow: {response_time_ms:.0f}ms")
            elif response.status_code == 401:
                self.on_start()  # Re-authenticate
                response.failure("Token expired")
            else:
                response.failure(f"Chunk upload failed: {response.status_code}")
    
    def complete_upload(self):
        """
        Complete the file upload and trigger merge.
        """
        if not self.current_upload:
            return
        
        upload_id = self.current_upload["upload_id"]
        
        with self.client.post(
            f"/v1/files/{upload_id}/complete",
            headers=self.headers,
            catch_response=True,
            name="/v1/files/{id}/complete"
        ) as response:
            if response.status_code == 202:
                response.success()
                # Reset for next upload
                self.current_upload = None
                self.uploaded_chunks = 0
            else:
                response.failure(f"Complete failed: {response.status_code}")
    
    def check_status(self):
        """
        Check upload status (used for monitoring).
        """
        if not self.current_upload:
            return
        
        upload_id = self.current_upload["upload_id"]
        
        with self.client.get(
            f"/v1/files/{upload_id}/status",
            headers=self.headers,
            catch_response=True,
            name="/v1/files/{id}/status"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status check failed: {response.status_code}")


# Custom metrics
total_chunks_uploaded = 0
total_bytes_uploaded = 0
slow_chunks = 0


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """
    Initialize test.
    """
    print("=" * 80)
    print("File Upload Performance Load Test")
    print("=" * 80)
    print(f"Target: 100 concurrent 1GB file uploads")
    print(f"Target chunk upload time: <5s per 10MB chunk")
    print(f"Host: {environment.host}")
    print("=" * 80)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """
    Test started.
    """
    global total_chunks_uploaded, total_bytes_uploaded, slow_chunks
    total_chunks_uploaded = 0
    total_bytes_uploaded = 0
    slow_chunks = 0
    print(f"Test started at {datetime.utcnow().isoformat()}")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """
    Track chunk upload statistics.
    """
    global total_chunks_uploaded, total_bytes_uploaded, slow_chunks
    
    if name == "/v1/files/{id}/chunks" and not exception:
        total_chunks_uploaded += 1
        total_bytes_uploaded += response_length
        
        # Track slow chunks (>5s for 10MB)
        if response_time > 5000:
            slow_chunks += 1


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """
    Calculate and display results.
    """
    stats = environment.stats
    
    print("\n" + "=" * 80)
    print("FILE UPLOAD LOAD TEST RESULTS")
    print("=" * 80)
    
    # Chunk upload statistics
    chunk_stats = stats.get("/v1/files/{id}/chunks", "POST")
    if chunk_stats and chunk_stats.num_requests > 0:
        print(f"\nChunk Upload Statistics:")
        print(f"  Total Chunks: {chunk_stats.num_requests:,}")
        print(f"  Successful: {chunk_stats.num_requests - chunk_stats.num_failures:,}")
        print(f"  Failed: {chunk_stats.num_failures:,}")
        print(f"  Success Rate: {((chunk_stats.num_requests - chunk_stats.num_failures) / chunk_stats.num_requests * 100):.2f}%")
        print(f"  Total Data: {total_bytes_uploaded / (1024**3):.2f} GB")
        
        print(f"\n  Chunk Upload Latency:")
        print(f"    Avg: {chunk_stats.avg_response_time:.0f}ms")
        print(f"    p50: {chunk_stats.get_response_time_percentile(0.50):.0f}ms")
        print(f"    p95: {chunk_stats.get_response_time_percentile(0.95):.0f}ms")
        print(f"    p99: {chunk_stats.get_response_time_percentile(0.99):.0f}ms")
        print(f"    Target: <5000ms (5s)")
        
        # Check target
        avg_time = chunk_stats.avg_response_time
        if avg_time < 5000:
            print(f"    ✓ PASSED (avg={avg_time:.0f}ms)")
        else:
            print(f"    ✗ FAILED (avg={avg_time:.0f}ms)")
        
        print(f"\n  Slow Chunks (>5s): {slow_chunks:,} ({slow_chunks / chunk_stats.num_requests * 100:.2f}%)")
    
    # Initiate statistics
    initiate_stats = stats.get("/v1/files/initiate", "POST")
    if initiate_stats and initiate_stats.num_requests > 0:
        print(f"\nUpload Initiation Statistics:")
        print(f"  Total Uploads Started: {initiate_stats.num_requests:,}")
        print(f"  Successful: {initiate_stats.num_requests - initiate_stats.num_failures:,}")
        print(f"  Avg Time: {initiate_stats.avg_response_time:.0f}ms")
    
    # Complete statistics
    complete_stats = stats.get("/v1/files/{id}/complete", "POST")
    if complete_stats and complete_stats.num_requests > 0:
        print(f"\nUpload Completion Statistics:")
        print(f"  Total Uploads Completed: {complete_stats.num_requests:,}")
        print(f"  Successful: {complete_stats.num_requests - complete_stats.num_failures:,}")
        print(f"  Avg Time: {complete_stats.avg_response_time:.0f}ms")
    
    # Throughput
    if stats.total.start_time:
        duration_seconds = (datetime.utcnow().timestamp() - stats.total.start_time)
        if duration_seconds > 0:
            throughput_mbps = (total_bytes_uploaded / duration_seconds) / (1024**2)
            print(f"\nThroughput:")
            print(f"  Duration: {duration_seconds:.2f}s")
            print(f"  Upload Throughput: {throughput_mbps:.2f} MB/s")
    
    print("=" * 80)


if __name__ == "__main__":
    """
    Run test with default settings.
    """
    import os
    import sys
    
    # Check if Locust is installed
    try:
        import locust
    except ImportError:
        print("ERROR: Locust is not installed.")
        print("Install with: pip install locust")
        sys.exit(1)
    
    # Run Locust
    os.system(
        f"locust -f {__file__} "
        f"--host=http://localhost:8000 "
        f"--users=10 "
        f"--spawn-rate=2 "
        f"--run-time=5m "
        f"--headless"
    )
