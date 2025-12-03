"""
Load Test: API Throughput

Tests the API's ability to handle high message throughput.
Target: 10M messages/minute (166K msg/s)

This test uses Locust to simulate concurrent users sending messages
and measures throughput, latency, and error rates.

Usage:
    # Run with web UI
    locust -f tests/load/test_api_throughput.py --host=http://localhost:8000

    # Run headless
    locust -f tests/load/test_api_throughput.py --host=http://localhost:8000 \
           --users=1000 --spawn-rate=100 --run-time=5m --headless

    # Run distributed (multiple workers)
    locust -f tests/load/test_api_throughput.py --host=http://localhost:8000 \
           --master --expect-workers=4
"""
import json
import uuid
import random
from locust import HttpUser, task, between, events
from datetime import datetime


class MessageSender(HttpUser):
    """
    Simulates a user sending messages through the API.
    
    Each user authenticates once and then sends messages to random conversations.
    """
    
    # Wait 0.1-0.5 seconds between requests (2-10 req/s per user)
    wait_time = between(0.1, 0.5)
    
    def on_start(self):
        """
        Called when a simulated user starts.
        Authenticates and gets an access token.
        """
        # Authenticate (using test users user1-user10)
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
    
    @task(10)
    def send_text_message(self):
        """
        Send a text message to a random conversation.
        Weight: 10 (90% of requests)
        """
        if not self.access_token:
            return
        
        conversation_id = random.randint(1, 50)  # Random conversation
        message_id = str(uuid.uuid4())
        
        payload = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "payload": {
                "type": "text",
                "content": f"Load test message at {datetime.utcnow().isoformat()}"
            },
            "channels": random.choice([
                ["whatsapp"],
                ["instagram"],
                ["whatsapp", "instagram"],
                ["all"]
            ])
        }
        
        with self.client.post(
            "/v1/messages",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="/v1/messages [text]"
        ) as response:
            if response.status_code == 202:
                response.success()
            elif response.status_code == 401:
                # Token expired, re-authenticate
                self.on_start()
                response.failure("Token expired, re-authenticating")
            else:
                response.failure(f"Unexpected status: {response.status_code}")
    
    @task(1)
    def send_file_message(self):
        """
        Send a file message (simulated - file already uploaded).
        Weight: 1 (10% of requests)
        """
        if not self.access_token:
            return
        
        conversation_id = random.randint(1, 50)
        message_id = str(uuid.uuid4())
        file_id = str(uuid.uuid4())  # Simulated uploaded file
        
        payload = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "payload": {
                "type": "file",
                "file_id": file_id
            },
            "channels": ["all"]
        }
        
        with self.client.post(
            "/v1/messages",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="/v1/messages [file]"
        ) as response:
            # File messages will likely fail (file not found)
            # but we're testing throughput, not business logic
            if response.status_code in [202, 400]:
                response.success()
            elif response.status_code == 401:
                self.on_start()
                response.failure("Token expired")
            else:
                response.failure(f"Unexpected status: {response.status_code}")
    
    @task(2)
    def list_conversations(self):
        """
        List user's conversations (read operation).
        Weight: 2 (lighter read load)
        """
        if not self.access_token:
            return
        
        with self.client.get(
            "/v1/conversations",
            params={"limit": 20, "offset": 0},
            headers=self.headers,
            catch_response=True,
            name="/v1/conversations"
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                self.on_start()
                response.failure("Token expired")
            else:
                response.failure(f"Unexpected status: {response.status_code}")
    
    @task(1)
    def get_conversation_messages(self):
        """
        Get messages from a conversation (read operation).
        Weight: 1
        """
        if not self.access_token:
            return
        
        conversation_id = random.randint(1, 50)
        
        with self.client.get(
            f"/v1/conversations/{conversation_id}/messages",
            params={"limit": 50, "offset": 0},
            headers=self.headers,
            catch_response=True,
            name="/v1/conversations/{id}/messages"
        ) as response:
            if response.status_code in [200, 403, 404]:
                # 403/404 expected for conversations user isn't member of
                response.success()
            elif response.status_code == 401:
                self.on_start()
                response.failure("Token expired")
            else:
                response.failure(f"Unexpected status: {response.status_code}")


# Custom metrics
@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """
    Initialize custom metrics tracking.
    """
    print("=" * 80)
    print("API Throughput Load Test")
    print("=" * 80)
    print(f"Target: 10M messages/minute (166,667 msg/s)")
    print(f"Host: {environment.host}")
    print("=" * 80)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """
    Called when test starts.
    """
    print(f"Test started at {datetime.utcnow().isoformat()}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """
    Called when test stops.
    Calculate and display throughput metrics.
    """
    stats = environment.stats
    total_requests = stats.total.num_requests
    total_failures = stats.total.num_failures
    
    print("\n" + "=" * 80)
    print("LOAD TEST RESULTS")
    print("=" * 80)
    
    # Calculate throughput
    if stats.total.start_time:
        duration_seconds = (datetime.utcnow().timestamp() - stats.total.start_time)
        requests_per_second = total_requests / duration_seconds if duration_seconds > 0 else 0
        messages_per_minute = requests_per_second * 60
        
        print(f"Total Requests: {total_requests:,}")
        print(f"Total Failures: {total_failures:,}")
        print(f"Success Rate: {((total_requests - total_failures) / total_requests * 100):.2f}%")
        print(f"Duration: {duration_seconds:.2f}s")
        print(f"Throughput: {requests_per_second:.2f} req/s")
        print(f"Throughput: {messages_per_minute:,.0f} msg/min")
        print(f"Target: 10,000,000 msg/min")
        print(f"Achievement: {(messages_per_minute / 10_000_000 * 100):.2f}%")
        
        # Latency percentiles
        print("\nLatency Percentiles:")
        print(f"  50th percentile: {stats.total.get_response_time_percentile(0.50):.0f}ms")
        print(f"  95th percentile: {stats.total.get_response_time_percentile(0.95):.0f}ms")
        print(f"  99th percentile: {stats.total.get_response_time_percentile(0.99):.0f}ms")
        print(f"  Target p99: <200ms")
        
        # Per-endpoint breakdown
        print("\nPer-Endpoint Statistics:")
        for name, stat in stats.entries.items():
            if stat.num_requests > 0:
                print(f"  {name}:")
                print(f"    Requests: {stat.num_requests:,}")
                print(f"    Failures: {stat.num_failures:,}")
                print(f"    Avg: {stat.avg_response_time:.0f}ms")
                print(f"    p99: {stat.get_response_time_percentile(0.99):.0f}ms")
    
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
        f"--users=100 "
        f"--spawn-rate=10 "
        f"--run-time=2m "
        f"--headless"
    )
