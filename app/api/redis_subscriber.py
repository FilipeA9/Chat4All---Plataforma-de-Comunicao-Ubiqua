"""
Redis Pub/Sub subscriber for real-time WebSocket notifications.

Subscribes to conversation and user channels, receives notifications from
workers/outbox poller, and forwards them to connected WebSocket clients.
"""
import logging
import asyncio
import json
from typing import Dict, Set, Callable, Optional
from redis import Redis
from redis.client import PubSub
from services.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class RedisPubSubSubscriber:
    """
    Redis Pub/Sub subscriber for WebSocket notifications.
    
    Manages subscriptions to conversation and user channels, receives
    messages from Redis, and forwards them to registered handlers.
    
    Supports:
    - conversation:{id} channels for conversation-specific events
    - user:{id} channels for user-specific notifications
    - global channel for system-wide announcements
    
    Thread-safe for async operations.
    """
    
    def __init__(self, connection_manager=None):
        """
        Initialize Redis Pub/Sub subscriber.
        
        Args:
            connection_manager: ConnectionManager instance to send notifications to
        """
        self.redis_client: Redis = get_redis_client()
        self.pubsub: PubSub = self.redis_client.pubsub(ignore_subscribe_messages=True)
        self.connection_manager = connection_manager
        self.subscribed_channels: Set[str] = set()
        self.is_running = False
        self._listen_task: Optional[asyncio.Task] = None
        
        logger.info("RedisPubSubSubscriber initialized")
    
    async def start(self):
        """
        Start the Pub/Sub listener in the background.
        
        Subscribes to the global channel and begins listening for messages.
        """
        if self.is_running:
            logger.warning("RedisPubSubSubscriber already running")
            return
        
        self.is_running = True
        
        # Subscribe to global channel
        await self.subscribe("global")
        
        # Start listening task
        self._listen_task = asyncio.create_task(self._listen())
        logger.info("RedisPubSubSubscriber started")
    
    async def stop(self):
        """
        Stop the Pub/Sub listener and unsubscribe from all channels.
        """
        if not self.is_running:
            return
        
        self.is_running = False
        
        # Cancel listen task
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        
        # Unsubscribe from all channels
        if self.subscribed_channels:
            await asyncio.to_thread(self.pubsub.unsubscribe, *self.subscribed_channels)
            self.subscribed_channels.clear()
        
        # Close pubsub connection
        await asyncio.to_thread(self.pubsub.close)
        
        logger.info("RedisPubSubSubscriber stopped")
    
    async def subscribe(self, channel: str):
        """
        Subscribe to a Redis Pub/Sub channel.
        
        Args:
            channel: Channel name (e.g., "conversation:123", "user:5", "global")
        """
        if channel in self.subscribed_channels:
            return
        
        try:
            await asyncio.to_thread(self.pubsub.subscribe, channel)
            self.subscribed_channels.add(channel)
            logger.debug(f"Subscribed to channel: {channel}")
        except Exception as e:
            logger.error(f"Failed to subscribe to channel {channel}: {e}")
    
    async def unsubscribe(self, channel: str):
        """
        Unsubscribe from a Redis Pub/Sub channel.
        
        Args:
            channel: Channel name to unsubscribe from
        """
        if channel not in self.subscribed_channels:
            return
        
        try:
            await asyncio.to_thread(self.pubsub.unsubscribe, channel)
            self.subscribed_channels.discard(channel)
            logger.debug(f"Unsubscribed from channel: {channel}")
        except Exception as e:
            logger.error(f"Failed to unsubscribe from channel {channel}: {e}")
    
    async def subscribe_to_conversation(self, conversation_id: int):
        """
        Subscribe to a conversation channel.
        
        Args:
            conversation_id: Conversation ID
        """
        channel = f"conversation:{conversation_id}"
        await self.subscribe(channel)
    
    async def subscribe_to_conversations_batch(self, conversation_ids: list[int]):
        """
        Subscribe to multiple conversation channels using Redis pipelining.
        
        This is more efficient than calling subscribe_to_conversation() multiple
        times as it reduces round trips to Redis.
        
        Args:
            conversation_ids: List of conversation IDs to subscribe to
        """
        if not conversation_ids:
            return
        
        channels = [f"conversation:{conv_id}" for conv_id in conversation_ids]
        
        # Filter out already subscribed channels
        new_channels = [ch for ch in channels if ch not in self.subscribed_channels]
        
        if not new_channels:
            logger.debug("All channels already subscribed")
            return
        
        try:
            # Use Redis pipelining to batch SUBSCRIBE commands
            await asyncio.to_thread(self.pubsub.subscribe, *new_channels)
            
            # Update tracking
            self.subscribed_channels.update(new_channels)
            
            logger.info(f"Batch subscribed to {len(new_channels)} conversation channels")
        except Exception as e:
            logger.error(f"Failed to batch subscribe to conversations: {e}")
    
    async def unsubscribe_from_conversation(self, conversation_id: int):
        """
        Unsubscribe from a conversation channel.
        
        Args:
            conversation_id: Conversation ID
        """
        channel = f"conversation:{conversation_id}"
        await self.unsubscribe(channel)
    
    async def unsubscribe_from_conversations_batch(self, conversation_ids: list[int]):
        """
        Unsubscribe from multiple conversation channels using Redis pipelining.
        
        Args:
            conversation_ids: List of conversation IDs to unsubscribe from
        """
        if not conversation_ids:
            return
        
        channels = [f"conversation:{conv_id}" for conv_id in conversation_ids]
        
        # Filter to only subscribed channels
        subscribed = [ch for ch in channels if ch in self.subscribed_channels]
        
        if not subscribed:
            logger.debug("No subscribed channels to unsubscribe from")
            return
        
        try:
            # Use Redis pipelining to batch UNSUBSCRIBE commands
            await asyncio.to_thread(self.pubsub.unsubscribe, *subscribed)
            
            # Update tracking
            self.subscribed_channels.difference_update(subscribed)
            
            logger.info(f"Batch unsubscribed from {len(subscribed)} conversation channels")
        except Exception as e:
            logger.error(f"Failed to batch unsubscribe from conversations: {e}")
    
    async def subscribe_to_user(self, user_id: int):
        """
        Subscribe to a user channel.
        
        Args:
            user_id: User ID
        """
        channel = f"user:{user_id}"
        await self.subscribe(channel)
    
    async def unsubscribe_from_user(self, user_id: int):
        """
        Unsubscribe from a user channel.
        
        Args:
            user_id: User ID
        """
        channel = f"user:{user_id}"
        await self.unsubscribe(channel)
    
    async def _listen(self):
        """
        Background task to listen for Redis Pub/Sub messages.
        
        Continuously polls for messages and forwards them to the
        appropriate handlers (ConnectionManager).
        """
        logger.info("Redis Pub/Sub listener started")
        
        while self.is_running:
            try:
                # Get message from Redis (blocking with timeout)
                message = await asyncio.to_thread(
                    self.pubsub.get_message,
                    timeout=1.0
                )
                
                if message and message.get("type") == "message":
                    await self._handle_message(message)
            
            except Exception as e:
                logger.error(f"Error in Redis Pub/Sub listener: {e}")
                await asyncio.sleep(1)  # Back off on error
        
        logger.info("Redis Pub/Sub listener stopped")
    
    async def _handle_message(self, message: dict):
        """
        Handle a received Pub/Sub message.
        
        Parses the message, determines the target (conversation/user/global),
        and forwards to the ConnectionManager.
        
        Args:
            message: Redis Pub/Sub message dict
        """
        try:
            channel = message.get("channel")
            data_str = message.get("data")
            
            if not channel or not data_str:
                return
            
            # Parse message data
            try:
                data = json.loads(data_str) if isinstance(data_str, str) else data_str
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in message from channel {channel}: {data_str}")
                return
            
            logger.debug(f"Received message on channel {channel}: {data.get('type', 'unknown')}")
            
            # Route to appropriate handler
            if channel == "global":
                await self._handle_global_message(data)
            elif channel.startswith("conversation:"):
                conversation_id = int(channel.split(":")[1])
                await self._handle_conversation_message(conversation_id, data)
            elif channel.startswith("user:"):
                user_id = int(channel.split(":")[1])
                await self._handle_user_message(user_id, data)
            else:
                logger.warning(f"Unknown channel type: {channel}")
        
        except Exception as e:
            logger.error(f"Error handling Pub/Sub message: {e}")
    
    async def _handle_global_message(self, data: dict):
        """
        Handle global broadcast message.
        
        Sends to all connected users.
        
        Args:
            data: Message data dict
        """
        if not self.connection_manager:
            return
        
        # Broadcast to all connected users
        for user_id in list(self.connection_manager.active_connections.keys()):
            try:
                await self.connection_manager.send_to_user(user_id, data)
            except Exception as e:
                logger.error(f"Error broadcasting to user {user_id}: {e}")
    
    async def _handle_conversation_message(self, conversation_id: int, data: dict):
        """
        Handle conversation-specific message.
        
        Sends to all connections subscribed to this conversation.
        
        Args:
            conversation_id: Conversation ID
            data: Message data dict
        """
        if not self.connection_manager:
            return
        
        # Get sender_id from message to exclude from broadcast (optional)
        sender_id = data.get("sender_id")
        
        try:
            await self.connection_manager.send_to_conversation(
                conversation_id,
                data,
                exclude_user_id=sender_id
            )
        except Exception as e:
            logger.error(f"Error sending to conversation {conversation_id}: {e}")
    
    async def _handle_user_message(self, user_id: int, data: dict):
        """
        Handle user-specific message.
        
        Sends to all connections for this user.
        
        Args:
            user_id: User ID
            data: Message data dict
        """
        if not self.connection_manager:
            return
        
        try:
            await self.connection_manager.send_to_user(user_id, data)
        except Exception as e:
            logger.error(f"Error sending to user {user_id}: {e}")
    
    def get_subscription_count(self) -> int:
        """
        Get number of active subscriptions.
        
        Returns:
            Number of subscribed channels
        """
        return len(self.subscribed_channels)


# Global subscriber instance
_subscriber: Optional[RedisPubSubSubscriber] = None


def get_redis_subscriber(connection_manager=None) -> RedisPubSubSubscriber:
    """
    Get global Redis Pub/Sub subscriber instance.
    
    Args:
        connection_manager: ConnectionManager instance (required on first call)
        
    Returns:
        RedisPubSubSubscriber instance
    """
    global _subscriber
    if _subscriber is None:
        if connection_manager is None:
            raise ValueError("connection_manager required to initialize subscriber")
        _subscriber = RedisPubSubSubscriber(connection_manager)
    return _subscriber


async def start_redis_subscriber(connection_manager):
    """
    Start the Redis Pub/Sub subscriber.
    
    Should be called during application startup.
    
    Args:
        connection_manager: ConnectionManager instance
    """
    subscriber = get_redis_subscriber(connection_manager)
    await subscriber.start()
    logger.info("Redis Pub/Sub subscriber started")


async def stop_redis_subscriber():
    """
    Stop the Redis Pub/Sub subscriber.
    
    Should be called during application shutdown.
    """
    global _subscriber
    if _subscriber:
        await _subscriber.stop()
        _subscriber = None
        logger.info("Redis Pub/Sub subscriber stopped")
