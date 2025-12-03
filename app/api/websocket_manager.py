"""
WebSocket Connection Manager for real-time message notifications.

Manages active WebSocket connections, tracks subscriptions, and routes
notifications to connected clients across multiple API instances using Redis Pub/Sub.
"""
import logging
import asyncio
import json
from typing import Dict, List, Set
from collections import defaultdict
from fastapi import WebSocket
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Import metrics (will be None if prometheus_client not installed)
try:
    from api.metrics import (
        websocket_connections_active, websocket_connections_total,
        websocket_disconnections_total, websocket_messages_sent_total,
        websocket_messages_received_total, update_websocket_metrics
    )
    METRICS_ENABLED = True
except ImportError:
    METRICS_ENABLED = False
    logger.warning("Prometheus metrics not available - install prometheus_client")


class ConnectionManager:
    """
    Manages active WebSocket connections for real-time notifications.
    
    Features:
    - Tracks connections per user (multiple devices/tabs supported)
    - Manages conversation subscriptions per connection
    - Enforces connection limits per user (max 5 concurrent)
    - Handles graceful disconnection and cleanup
    - Routes notifications to appropriate connections
    
    Thread-safe for async operations.
    """
    
    def __init__(self):
        """Initialize connection manager with empty connection tracking."""
        # {user_id: List[WebSocket]} - tracks all connections per user
        self.active_connections: Dict[int, List[WebSocket]] = defaultdict(list)
        
        # {WebSocket: user_id} - reverse lookup for user by connection
        self.connection_to_user: Dict[WebSocket, int] = {}
        
        # {WebSocket: Set[conversation_id]} - tracks conversation subscriptions per connection
        self.connection_subscriptions: Dict[WebSocket, Set[int]] = defaultdict(set)
        
        # {WebSocket: datetime} - tracks last heartbeat received
        self.last_heartbeat: Dict[WebSocket, datetime] = {}
        
        # Connection limits
        self.MAX_CONNECTIONS_PER_USER = 5
        
        logger.info("ConnectionManager initialized")
    
    async def connect(self, websocket: WebSocket, user_id: int) -> bool:
        """
        Accept a new WebSocket connection for a user.
        
        Enforces connection limits (max 5 per user). If limit is reached,
        rejects the connection.
        
        Args:
            websocket: WebSocket connection to accept
            user_id: ID of the authenticated user
            
        Returns:
            True if connection accepted, False if limit reached
        """
        # Check connection limit
        current_connections = len(self.active_connections[user_id])
        if current_connections >= self.MAX_CONNECTIONS_PER_USER:
            logger.warning(
                f"Connection limit reached for user {user_id}: "
                f"{current_connections}/{self.MAX_CONNECTIONS_PER_USER}"
            )
            return False
        
        # Accept connection
        await websocket.accept()
        
        # Track connection
        self.active_connections[user_id].append(websocket)
        self.connection_to_user[websocket] = user_id
        self.last_heartbeat[websocket] = datetime.utcnow()
        
        # Update metrics
        if METRICS_ENABLED:
            websocket_connections_total.labels(instance="api").inc()
        
        logger.info(
            f"User {user_id} connected via WebSocket "
            f"(total connections: {len(self.active_connections[user_id])})"
        )
        
        return True
    
    def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection and clean up tracking.
        
        Removes from all tracking dictionaries: active connections,
        reverse lookup, subscriptions, and heartbeat tracking.
        
        Args:
            websocket: WebSocket connection to remove
        """
        user_id = self.connection_to_user.get(websocket)
        
        if user_id is not None:
            # Remove from active connections
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            
            # Clean up empty user entry
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
            
            # Remove reverse lookup
            del self.connection_to_user[websocket]
            
            # Remove subscriptions
            if websocket in self.connection_subscriptions:
                del self.connection_subscriptions[websocket]
            
            # Remove heartbeat tracking
            if websocket in self.last_heartbeat:
                del self.last_heartbeat[websocket]
            
            # Update metrics
            if METRICS_ENABLED:
                websocket_disconnections_total.labels(instance="api", reason="normal").inc()
            
            logger.info(
                f"User {user_id} disconnected from WebSocket "
                f"(remaining connections: {len(self.active_connections.get(user_id, []))})"
            )
    
    def subscribe_to_conversation(self, websocket: WebSocket, conversation_id: int):
        """
        Subscribe a connection to receive notifications for a conversation.
        
        Args:
            websocket: WebSocket connection to subscribe
            conversation_id: ID of conversation to subscribe to
        """
        self.connection_subscriptions[websocket].add(conversation_id)
        user_id = self.connection_to_user.get(websocket)
        logger.debug(f"User {user_id} subscribed to conversation {conversation_id}")
    
    def unsubscribe_from_conversation(self, websocket: WebSocket, conversation_id: int):
        """
        Unsubscribe a connection from conversation notifications.
        
        Args:
            websocket: WebSocket connection to unsubscribe
            conversation_id: ID of conversation to unsubscribe from
        """
        if websocket in self.connection_subscriptions:
            self.connection_subscriptions[websocket].discard(conversation_id)
            user_id = self.connection_to_user.get(websocket)
            logger.debug(f"User {user_id} unsubscribed from conversation {conversation_id}")
    
    async def send_to_user(self, user_id: int, message: dict):
        """
        Send a message to all connections for a specific user.
        
        Broadcasts to all devices/tabs the user has open. Handles connection
        errors gracefully by removing stale connections.
        
        Args:
            user_id: ID of user to send message to
            message: Message dict to send (will be JSON-encoded)
        """
        connections = self.active_connections.get(user_id, [])
        if not connections:
            logger.debug(f"No active connections for user {user_id}")
            return
        
        # Send to all user's connections
        stale_connections = []
        for connection in connections:
            try:
                await connection.send_json(message)
                logger.debug(f"Sent message to user {user_id}: {message.get('type', 'unknown')}")
            except Exception as e:
                logger.error(f"Error sending to user {user_id}: {e}")
                stale_connections.append(connection)
        
        # Clean up stale connections
        for connection in stale_connections:
            self.disconnect(connection)
    
    async def send_to_conversation(self, conversation_id: int, message: dict, exclude_user_id: int = None):
        """
        Send a message to all connections subscribed to a conversation.
        
        Optionally excludes the sender to avoid echo. Broadcasts to all
        conversation members who are currently connected.
        
        Args:
            conversation_id: ID of conversation to broadcast to
            message: Message dict to send (will be JSON-encoded)
            exclude_user_id: Optional user ID to exclude from broadcast (typically the sender)
        """
        sent_count = 0
        stale_connections = []
        
        # Find all connections subscribed to this conversation
        for connection, subscriptions in self.connection_subscriptions.items():
            if conversation_id not in subscriptions:
                continue
            
            user_id = self.connection_to_user.get(connection)
            if exclude_user_id and user_id == exclude_user_id:
                continue
            
            try:
                await connection.send_json(message)
                sent_count += 1
                logger.debug(
                    f"Sent message to user {user_id} for conversation {conversation_id}"
                )
            except Exception as e:
                logger.error(
                    f"Error sending to user {user_id} for conversation {conversation_id}: {e}"
                )
                stale_connections.append(connection)
        
        # Clean up stale connections
        for connection in stale_connections:
            self.disconnect(connection)
        
        if sent_count > 0:
            logger.info(
                f"Broadcast to conversation {conversation_id}: {sent_count} connections"
            )
    
    async def update_heartbeat(self, websocket: WebSocket):
        """
        Update last heartbeat timestamp for a connection.
        
        Called when a pong is received in response to a ping.
        
        Args:
            websocket: WebSocket connection to update
        """
        self.last_heartbeat[websocket] = datetime.utcnow()
        user_id = self.connection_to_user.get(websocket)
        logger.debug(f"Heartbeat updated for user {user_id}")
    
    def get_stale_connections(self, timeout_seconds: int = 40) -> List[WebSocket]:
        """
        Find connections that haven't sent a heartbeat recently.
        
        Used by heartbeat monitor to detect and close dead connections.
        
        Args:
            timeout_seconds: Seconds since last heartbeat to consider stale (default: 40s)
            
        Returns:
            List of stale WebSocket connections
        """
        now = datetime.utcnow()
        timeout_delta = timedelta(seconds=timeout_seconds)
        
        stale = []
        for connection, last_beat in self.last_heartbeat.items():
            if now - last_beat > timeout_delta:
                stale.append(connection)
        
        return stale
    
    def get_connection_count(self) -> int:
        """
        Get total number of active connections across all users.
        
        Returns:
            Total connection count
        """
        return sum(len(connections) for connections in self.active_connections.values())
    
    def get_user_count(self) -> int:
        """
        Get number of unique users currently connected.
        
        Returns:
            Unique user count
        """
        return len(self.active_connections)
    
    def get_user_connections(self, user_id: int) -> List[WebSocket]:
        """
        Get all active connections for a specific user.
        
        Args:
            user_id: User ID to query
            
        Returns:
            List of WebSocket connections for the user
        """
        return self.active_connections.get(user_id, [])


# Global connection manager instance
connection_manager = ConnectionManager()


async def heartbeat_monitor(interval_seconds: int = 30, timeout_seconds: int = 40):
    """
    Background task to send heartbeat pings and detect stale connections.
    
    Sends ping every 30 seconds, expects pong within 10 seconds.
    Closes connections that haven't responded in 40 seconds.
    Also updates Prometheus metrics periodically.
    
    Args:
        interval_seconds: Seconds between ping messages (default: 30)
        timeout_seconds: Seconds without heartbeat before closing (default: 40)
    """
    logger.info(f"Heartbeat monitor started (interval={interval_seconds}s, timeout={timeout_seconds}s)")
    
    while True:
        await asyncio.sleep(interval_seconds)
        
        try:
            # Send ping to all connections
            ping_message = {"type": "ping", "timestamp": datetime.utcnow().isoformat()}
            
            for user_id, connections in list(connection_manager.active_connections.items()):
                for connection in connections:
                    try:
                        await connection.send_json(ping_message)
                        if METRICS_ENABLED:
                            websocket_messages_sent_total.labels(
                                message_type="ping",
                                instance="api"
                            ).inc()
                    except Exception as e:
                        logger.error(f"Error sending ping to user {user_id}: {e}")
            
            # Find and close stale connections
            stale_connections = connection_manager.get_stale_connections(timeout_seconds)
            for connection in stale_connections:
                user_id = connection_manager.connection_to_user.get(connection)
                logger.warning(f"Closing stale connection for user {user_id}")
                
                try:
                    await connection.close(code=1000, reason="Connection timeout")
                except:
                    pass
                
                if METRICS_ENABLED:
                    websocket_disconnections_total.labels(
                        instance="api",
                        reason="timeout"
                    ).inc()
                
                connection_manager.disconnect(connection)
            
            # Update metrics
            if METRICS_ENABLED:
                update_websocket_metrics(connection_manager)
            
            # Log stats
            total_connections = connection_manager.get_connection_count()
            unique_users = connection_manager.get_user_count()
            logger.info(
                f"Heartbeat complete: {total_connections} connections, {unique_users} users"
            )
        
        except Exception as e:
            logger.error(f"Error in heartbeat monitor: {e}")
