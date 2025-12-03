"""
Load Test: WebSocket Connections

Tests the system's ability to maintain 10K concurrent WebSocket connections
and deliver real-time notifications with <100ms latency.

Usage:
    # Run with web UI
    locust -f tests/load/test_websocket_connections.py --host=ws://localhost:8000

    # Run headless (10K users)
    locust -f tests/load/test_websocket_connections.py --host=ws://localhost:8000 \
           --users=10000 --spawn-rate=1000 --run-time=10m --headless

    # Run with smaller load for testing
    locust -f tests/load/test_websocket_connections.py --host=ws://localhost:8000 \
           --users=100 --spawn-rate=10 --run-time=2m
"""
import json
import time
import random
from datetime import datetime
from locust import User, task, between, events
from locust.exception import StopUser
import websocket as ws_client


class WebSocketUser(User):
    """
    Simulates a user maintaining a WebSocket connection for real-time notifications.
    
    Each user:
    1. Authenticates to get JWT token
    2. Opens WebSocket connection with token
    3. Subscribes to random conversations
    4. Responds to ping/pong heartbeats
    5. Measures notification delivery latency
    """
    
    wait_time = between(5, 15)  # Wait 5-15s between actions
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ws = None
        self.access_token = None
        self.user_id = None
        self.connected = False
        self.message_latencies = []
    
    def on_start(self):
        """
        Authenticate and establish WebSocket connection.
        """
        # Get auth token via HTTP
        self.authenticate()
        
        if self.access_token:
            # Connect WebSocket
            self.connect_websocket()
            
            if self.connected:
                # Subscribe to random conversations
                self.subscribe_to_conversations()
    
    def on_stop(self):
        """
        Clean up WebSocket connection.
        """
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
    
    def authenticate(self):
        """
        Authenticate via HTTP API to get JWT token.
        """
        import requests
        
        user_id = random.randint(1, 10)
        
        try:
            response = requests.post(
                f"http://{self.host.replace('ws://', '').replace('/ws', '')}/auth/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": f"user{user_id}",
                    "client_secret": "password123",
                    "scope": "read write"
                },
                timeout=10
            )
            
            if response.status_code == 200:
                self.access_token = response.json()["access_token"]
                self.user_id = user_id
                return True
            else:
                print(f"Auth failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"Auth error: {e}")
            return False
    
    def connect_websocket(self):
        """
        Establish WebSocket connection with JWT authentication.
        """
        if not self.access_token:
            return
        
        ws_url = f"{self.host}/ws?token={self.access_token}"
        
        try:
            start_time = time.time()
            self.ws = ws_client.create_connection(
                ws_url,
                timeout=10,
                enable_multithread=True
            )
            connection_time = (time.time() - start_time) * 1000
            
            # Receive welcome message
            welcome = json.loads(self.ws.recv())
            
            if welcome.get("type") == "connected":
                self.connected = True
                
                # Fire Locust event for connection metric
                events.request.fire(
                    request_type="WSConn",
                    name="WebSocket Connect",
                    response_time=connection_time,
                    response_length=len(json.dumps(welcome)),
                    exception=None,
                    context={}
                )
                
                return True
            else:
                print(f"Unexpected welcome: {welcome}")
                return False
        
        except Exception as e:
            events.request.fire(
                request_type="WSConn",
                name="WebSocket Connect",
                response_time=0,
                response_length=0,
                exception=e,
                context={}
            )
            print(f"WebSocket connection failed: {e}")
            return False
    
    def subscribe_to_conversations(self):
        """
        Subscribe to 3-5 random conversations.
        """
        if not self.ws or not self.connected:
            return
        
        num_conversations = random.randint(3, 5)
        
        for _ in range(num_conversations):
            conversation_id = random.randint(1, 50)
            
            try:
                start_time = time.time()
                
                # Send subscribe command
                self.ws.send(json.dumps({
                    "action": "subscribe",
                    "conversation_id": conversation_id
                }))
                
                # Receive acknowledgment
                response = json.loads(self.ws.recv())
                
                response_time = (time.time() - start_time) * 1000
                
                if response.get("type") == "subscribed":
                    events.request.fire(
                        request_type="WSSub",
                        name="WebSocket Subscribe",
                        response_time=response_time,
                        response_length=len(json.dumps(response)),
                        exception=None,
                        context={}
                    )
                else:
                    raise Exception(f"Subscribe failed: {response}")
            
            except Exception as e:
                events.request.fire(
                    request_type="WSSub",
                    name="WebSocket Subscribe",
                    response_time=0,
                    response_length=0,
                    exception=e,
                    context={}
                )
    
    @task
    def heartbeat(self):
        """
        Respond to server ping with pong (heartbeat mechanism).
        """
        if not self.ws or not self.connected:
            raise StopUser()
        
        try:
            # Non-blocking receive with timeout
            self.ws.settimeout(0.1)
            
            try:
                message = self.ws.recv()
                data = json.loads(message)
                
                if data.get("type") == "ping":
                    start_time = time.time()
                    
                    # Send pong
                    self.ws.send(json.dumps({"action": "pong"}))
                    
                    response_time = (time.time() - start_time) * 1000
                    
                    events.request.fire(
                        request_type="WSPong",
                        name="WebSocket Pong",
                        response_time=response_time,
                        response_length=0,
                        exception=None,
                        context={}
                    )
                
                elif data.get("type") == "message.created":
                    # Measure notification delivery latency
                    created_at = data.get("created_at")
                    if created_at:
                        try:
                            created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            latency = (datetime.utcnow() - created_time).total_seconds() * 1000
                            self.message_latencies.append(latency)
                            
                            events.request.fire(
                                request_type="WSNotif",
                                name="WebSocket Notification",
                                response_time=latency,
                                response_length=len(message),
                                exception=None,
                                context={}
                            )
                        except:
                            pass
            
            except ws_client.WebSocketTimeoutException:
                # No message available, continue
                pass
        
        except Exception as e:
            print(f"Heartbeat error: {e}")
            self.connected = False
            raise StopUser()


# Custom metrics
connection_count = 0
notification_latencies = []


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """
    Initialize test.
    """
    print("=" * 80)
    print("WebSocket Connection Load Test")
    print("=" * 80)
    print(f"Target: 10,000 concurrent connections")
    print(f"Target notification latency: <100ms p99")
    print(f"Host: {environment.host}")
    print("=" * 80)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """
    Test started.
    """
    global connection_count, notification_latencies
    connection_count = 0
    notification_latencies = []
    print(f"Test started at {datetime.utcnow().isoformat()}")


@events.user_add.add_listener
def on_user_add(user, **kwargs):
    """
    Track active connections.
    """
    global connection_count
    if hasattr(user, 'connected') and user.connected:
        connection_count += 1


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """
    Calculate and display results.
    """
    stats = environment.stats
    
    print("\n" + "=" * 80)
    print("WEBSOCKET LOAD TEST RESULTS")
    print("=" * 80)
    
    # Connection statistics
    ws_conn_stats = stats.get("WebSocket Connect", "WSConn")
    if ws_conn_stats:
        print(f"\nConnection Statistics:")
        print(f"  Total Attempts: {ws_conn_stats.num_requests:,}")
        print(f"  Successful: {ws_conn_stats.num_requests - ws_conn_stats.num_failures:,}")
        print(f"  Failed: {ws_conn_stats.num_failures:,}")
        print(f"  Success Rate: {((ws_conn_stats.num_requests - ws_conn_stats.num_failures) / ws_conn_stats.num_requests * 100):.2f}%")
        print(f"  Avg Connection Time: {ws_conn_stats.avg_response_time:.0f}ms")
        print(f"  Peak Concurrent: {connection_count:,}")
        print(f"  Target: 10,000")
        print(f"  Achievement: {(connection_count / 10_000 * 100):.2f}%")
    
    # Notification latency
    ws_notif_stats = stats.get("WebSocket Notification", "WSNotif")
    if ws_notif_stats and ws_notif_stats.num_requests > 0:
        print(f"\nNotification Latency:")
        print(f"  Notifications Received: {ws_notif_stats.num_requests:,}")
        print(f"  Avg Latency: {ws_notif_stats.avg_response_time:.0f}ms")
        print(f"  p50: {ws_notif_stats.get_response_time_percentile(0.50):.0f}ms")
        print(f"  p95: {ws_notif_stats.get_response_time_percentile(0.95):.0f}ms")
        print(f"  p99: {ws_notif_stats.get_response_time_percentile(0.99):.0f}ms")
        print(f"  Target p99: <100ms")
        
        p99 = ws_notif_stats.get_response_time_percentile(0.99)
        if p99 < 100:
            print(f"  ✓ PASSED (p99={p99:.0f}ms)")
        else:
            print(f"  ✗ FAILED (p99={p99:.0f}ms)")
    
    # Heartbeat statistics
    ws_pong_stats = stats.get("WebSocket Pong", "WSPong")
    if ws_pong_stats and ws_pong_stats.num_requests > 0:
        print(f"\nHeartbeat Statistics:")
        print(f"  Pongs Sent: {ws_pong_stats.num_requests:,}")
        print(f"  Avg Response Time: {ws_pong_stats.avg_response_time:.0f}ms")
    
    print("=" * 80)


if __name__ == "__main__":
    """
    Run test with default settings.
    """
    import os
    import sys
    
    # Check dependencies
    try:
        import locust
        import websocket
    except ImportError as e:
        print(f"ERROR: Missing dependency: {e}")
        print("Install with: pip install locust websocket-client")
        sys.exit(1)
    
    # Run Locust
    os.system(
        f"locust -f {__file__} "
        f"--host=ws://localhost:8000 "
        f"--users=100 "
        f"--spawn-rate=10 "
        f"--run-time=2m "
        f"--headless"
    )
