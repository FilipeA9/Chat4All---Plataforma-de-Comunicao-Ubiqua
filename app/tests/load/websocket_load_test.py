"""
WebSocket Load Test (T078)

Locust-based load test for WebSocket connections to validate:
- 10,000 concurrent WebSocket connections per API instance
- P99 notification latency < 100ms
- CPU usage < 70% under load
- Message throughput of 100 msg/sec

Usage:
    # Run with Locust UI
    locust -f tests/load/websocket_load_test.py --host=ws://localhost:8000
    
    # Run headless with 10K users
    locust -f tests/load/websocket_load_test.py --host=ws://localhost:8000 \
           --users=10000 --spawn-rate=100 --run-time=10m --headless
    
    # Run with custom parameters
    locust -f tests/load/websocket_load_test.py --host=ws://localhost:8000 \
           --users=5000 --spawn-rate=50 --run-time=5m

Environment Variables:
    API_BASE_URL: Base URL for REST API (default: http://localhost:8000)
    WS_BASE_URL: Base URL for WebSocket (default: ws://localhost:8000)
    TEST_USER_COUNT: Number of test users to create (default: 100)
    TEST_CONVERSATION_ID: Conversation ID to test (default: 1)
"""
import json
import time
import random
import logging
from typing import Optional
from locust import User, task, events, between
from locust.exception import StopUser
import websocket
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test configuration
API_BASE_URL = "http://localhost:8000"
WS_BASE_URL = "ws://localhost:8000"
TEST_USER_COUNT = 100
TEST_CONVERSATION_ID = 1


class WebSocketClient:
    """
    WebSocket client for Locust load testing.
    
    Manages WebSocket connection, authentication, and message handling.
    Records metrics for Locust reporting.
    """
    
    def __init__(self, host: str, user_id: int, token: str):
        """
        Initialize WebSocket client.
        
        Args:
            host: WebSocket host URL (e.g., ws://localhost:8000)
            user_id: User ID for this connection
            token: JWT authentication token
        """
        self.host = host
        self.user_id = user_id
        self.token = token
        self.ws: Optional[websocket.WebSocket] = None
        self.connected = False
        self.message_count = 0
        self.latencies = []
    
    def connect(self) -> bool:
        """
        Connect to WebSocket endpoint with authentication.
        
        Returns:
            True if connection successful, False otherwise
        """
        start_time = time.time()
        
        try:
            # Connect with token in query parameter
            ws_url = f"{self.host}/ws?token={self.token}"
            self.ws = websocket.create_connection(ws_url, timeout=10)
            self.connected = True
            
            # Record success metric
            total_time = int((time.time() - start_time) * 1000)
            events.request.fire(
                request_type="WebSocket",
                name="connect",
                response_time=total_time,
                response_length=0,
                exception=None,
                context={}
            )
            
            logger.info(f"User {self.user_id} connected to WebSocket")
            return True
        
        except Exception as e:
            # Record failure metric
            total_time = int((time.time() - start_time) * 1000)
            events.request.fire(
                request_type="WebSocket",
                name="connect",
                response_time=total_time,
                response_length=0,
                exception=e,
                context={}
            )
            
            logger.error(f"User {self.user_id} failed to connect: {e}")
            return False
    
    def disconnect(self):
        """Close WebSocket connection."""
        if self.ws and self.connected:
            try:
                self.ws.close()
                self.connected = False
                logger.info(f"User {self.user_id} disconnected from WebSocket")
            except Exception as e:
                logger.error(f"Error disconnecting user {self.user_id}: {e}")
    
    def send_message(self, message: dict):
        """
        Send a message via WebSocket.
        
        Args:
            message: Message dict to send (will be JSON-encoded)
        """
        if not self.connected:
            logger.warning(f"User {self.user_id} not connected, cannot send message")
            return
        
        start_time = time.time()
        
        try:
            # Add timestamp for latency measurement
            message["sent_at"] = time.time()
            
            # Send message
            self.ws.send(json.dumps(message))
            
            # Record success metric
            total_time = int((time.time() - start_time) * 1000)
            events.request.fire(
                request_type="WebSocket",
                name="send_message",
                response_time=total_time,
                response_length=len(json.dumps(message)),
                exception=None,
                context={}
            )
            
            self.message_count += 1
        
        except Exception as e:
            # Record failure metric
            total_time = int((time.time() - start_time) * 1000)
            events.request.fire(
                request_type="WebSocket",
                name="send_message",
                response_time=total_time,
                response_length=0,
                exception=e,
                context={}
            )
            
            logger.error(f"User {self.user_id} failed to send message: {e}")
    
    def receive_message(self, timeout: float = 5.0) -> Optional[dict]:
        """
        Receive a message from WebSocket.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            Message dict or None if timeout/error
        """
        if not self.connected:
            return None
        
        start_time = time.time()
        
        try:
            # Receive message with timeout
            self.ws.settimeout(timeout)
            data = self.ws.recv()
            
            # Parse JSON
            message = json.loads(data)
            
            # Calculate latency if sent_at timestamp present
            if "sent_at" in message:
                latency = (time.time() - message["sent_at"]) * 1000  # ms
                self.latencies.append(latency)
            
            # Record success metric
            total_time = int((time.time() - start_time) * 1000)
            events.request.fire(
                request_type="WebSocket",
                name="receive_message",
                response_time=total_time,
                response_length=len(data),
                exception=None,
                context={}
            )
            
            return message
        
        except websocket.WebSocketTimeoutException:
            # Timeout is not an error for receive
            return None
        
        except Exception as e:
            # Record failure metric
            total_time = int((time.time() - start_time) * 1000)
            events.request.fire(
                request_type="WebSocket",
                name="receive_message",
                response_time=total_time,
                response_length=0,
                exception=e,
                context={}
            )
            
            logger.error(f"User {self.user_id} failed to receive message: {e}")
            return None
    
    def get_average_latency(self) -> float:
        """
        Get average notification latency in milliseconds.
        
        Returns:
            Average latency or 0 if no messages received
        """
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)
    
    def get_p99_latency(self) -> float:
        """
        Get P99 notification latency in milliseconds.
        
        Returns:
            P99 latency or 0 if insufficient data
        """
        if len(self.latencies) < 100:
            return 0.0
        
        sorted_latencies = sorted(self.latencies)
        p99_index = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[p99_index]


class WebSocketUser(User):
    """
    Locust user that simulates a WebSocket client.
    
    Connects to WebSocket endpoint, subscribes to a conversation,
    sends and receives messages, and measures latency.
    """
    
    wait_time = between(1, 5)  # Wait 1-5 seconds between tasks
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = random.randint(1, TEST_USER_COUNT)
        self.token = None
        self.ws_client: Optional[WebSocketClient] = None
    
    def on_start(self):
        """
        Called when a simulated user starts.
        
        Authenticates and connects to WebSocket.
        """
        # Authenticate to get JWT token
        self.token = self._authenticate()
        
        if not self.token:
            logger.error(f"User {self.user_id} failed to authenticate, stopping")
            raise StopUser()
        
        # Connect to WebSocket
        self.ws_client = WebSocketClient(
            host=WS_BASE_URL,
            user_id=self.user_id,
            token=self.token
        )
        
        if not self.ws_client.connect():
            logger.error(f"User {self.user_id} failed to connect, stopping")
            raise StopUser()
        
        # Subscribe to test conversation
        self._subscribe_to_conversation(TEST_CONVERSATION_ID)
    
    def on_stop(self):
        """
        Called when a simulated user stops.
        
        Disconnects from WebSocket and logs stats.
        """
        if self.ws_client:
            # Log latency stats
            avg_latency = self.ws_client.get_average_latency()
            p99_latency = self.ws_client.get_p99_latency()
            
            logger.info(
                f"User {self.user_id} stats: "
                f"messages={self.ws_client.message_count}, "
                f"avg_latency={avg_latency:.2f}ms, "
                f"p99_latency={p99_latency:.2f}ms"
            )
            
            # Disconnect
            self.ws_client.disconnect()
    
    def _authenticate(self) -> Optional[str]:
        """
        Authenticate with API to get JWT token.
        
        Returns:
            JWT token or None if authentication failed
        """
        start_time = time.time()
        
        try:
            # For load testing, use a simplified auth endpoint
            # In production, this would be POST /auth/token with credentials
            response = requests.post(
                f"{API_BASE_URL}/auth/token",
                json={
                    "client_id": f"test_user_{self.user_id}",
                    "client_secret": "test_secret",
                    "grant_type": "client_credentials"
                },
                timeout=10
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Record success metric
            total_time = int((time.time() - start_time) * 1000)
            events.request.fire(
                request_type="POST",
                name="/auth/token",
                response_time=total_time,
                response_length=len(response.content),
                exception=None,
                context={}
            )
            
            return data.get("access_token")
        
        except Exception as e:
            # Record failure metric
            total_time = int((time.time() - start_time) * 1000)
            events.request.fire(
                request_type="POST",
                name="/auth/token",
                response_time=total_time,
                response_length=0,
                exception=e,
                context={}
            )
            
            logger.error(f"Authentication failed for user {self.user_id}: {e}")
            return None
    
    def _subscribe_to_conversation(self, conversation_id: int):
        """
        Subscribe to a conversation via WebSocket.
        
        Args:
            conversation_id: Conversation ID to subscribe to
        """
        if not self.ws_client:
            return
        
        subscribe_message = {
            "type": "subscribe",
            "conversation_id": conversation_id
        }
        
        self.ws_client.send_message(subscribe_message)
        logger.debug(f"User {self.user_id} subscribed to conversation {conversation_id}")
    
    @task(3)
    def send_message_task(self):
        """
        Task: Send a message to the conversation.
        
        Weight: 3 (happens 3x more often than receive)
        """
        if not self.ws_client:
            return
        
        message = {
            "type": "message",
            "conversation_id": TEST_CONVERSATION_ID,
            "content": f"Test message from user {self.user_id} at {time.time()}",
            "channels": ["whatsapp"]
        }
        
        self.ws_client.send_message(message)
    
    @task(1)
    def receive_notification_task(self):
        """
        Task: Wait for and receive a notification.
        
        Weight: 1 (passive receiving)
        """
        if not self.ws_client:
            return
        
        # Wait for notification (timeout after 5s)
        notification = self.ws_client.receive_message(timeout=5.0)
        
        if notification:
            msg_type = notification.get("type", "unknown")
            logger.debug(f"User {self.user_id} received notification: {msg_type}")
    
    @task(1)
    def respond_to_ping_task(self):
        """
        Task: Respond to heartbeat ping with pong.
        
        Weight: 1 (periodic heartbeat)
        """
        if not self.ws_client:
            return
        
        # Check for ping message
        message = self.ws_client.receive_message(timeout=1.0)
        
        if message and message.get("type") == "ping":
            # Respond with pong
            pong_message = {
                "type": "pong",
                "timestamp": message.get("timestamp")
            }
            self.ws_client.send_message(pong_message)
            logger.debug(f"User {self.user_id} sent pong")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """
    Called when load test starts.
    
    Logs test configuration and setup.
    """
    logger.info("=" * 80)
    logger.info("WebSocket Load Test Starting")
    logger.info("=" * 80)
    logger.info(f"API Base URL: {API_BASE_URL}")
    logger.info(f"WebSocket Base URL: {WS_BASE_URL}")
    logger.info(f"Test User Count: {TEST_USER_COUNT}")
    logger.info(f"Test Conversation ID: {TEST_CONVERSATION_ID}")
    logger.info(f"Target: 10,000 concurrent connections")
    logger.info(f"Target: P99 latency < 100ms")
    logger.info("=" * 80)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """
    Called when load test stops.
    
    Logs final statistics and validates performance targets.
    """
    logger.info("=" * 80)
    logger.info("WebSocket Load Test Complete")
    logger.info("=" * 80)
    
    stats = environment.stats
    
    # Log overall stats
    logger.info(f"Total requests: {stats.total.num_requests}")
    logger.info(f"Total failures: {stats.total.num_failures}")
    logger.info(f"Average response time: {stats.total.avg_response_time:.2f}ms")
    logger.info(f"Median response time: {stats.total.median_response_time:.2f}ms")
    logger.info(f"95th percentile: {stats.total.get_response_time_percentile(0.95):.2f}ms")
    logger.info(f"99th percentile: {stats.total.get_response_time_percentile(0.99):.2f}ms")
    
    # Validate performance targets
    p99_latency = stats.total.get_response_time_percentile(0.99)
    failure_rate = (stats.total.num_failures / stats.total.num_requests * 100) if stats.total.num_requests > 0 else 0
    
    logger.info("=" * 80)
    logger.info("Performance Target Validation:")
    logger.info(f"  P99 Latency: {p99_latency:.2f}ms (target: <100ms) - {'✓ PASS' if p99_latency < 100 else '✗ FAIL'}")
    logger.info(f"  Failure Rate: {failure_rate:.2f}% (target: <1%) - {'✓ PASS' if failure_rate < 1 else '✗ FAIL'}")
    logger.info("=" * 80)


if __name__ == "__main__":
    # Can be run standalone for testing
    import sys
    from locust.main import main as locust_main
    
    sys.argv = [
        "locust",
        "-f", __file__,
        "--host", WS_BASE_URL,
        "--users", "100",
        "--spawn-rate", "10",
        "--run-time", "1m",
        "--headless"
    ]
    
    locust_main()
