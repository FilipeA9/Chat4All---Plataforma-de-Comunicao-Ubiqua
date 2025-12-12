"""
Redis client for caching, rate limiting, and Pub/Sub.
Provides connection pooling and utility functions.
Enhanced with circuit breaker for graceful degradation (T059).
"""
import os
import logging
from typing import Optional, Any
from redis import Redis, ConnectionPool
import json
import pybreaker

logger = logging.getLogger(__name__)

# Circuit breaker for Redis (T059)
redis_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=3,  # Open circuit after 3 failures
    #timeout=30,  # Keep circuit open for 30 seconds
    reset_timeout=15,  # Try half-open after 15 seconds
    name="redis_client",
    listeners=[
        lambda breaker, _: logger.warning(f"Circuit breaker {breaker.name} opened - Redis unavailable"),
        lambda breaker: logger.info(f"Circuit breaker {breaker.name} closed - Redis restored"),
        lambda breaker: logger.info(f"Circuit breaker {breaker.name} half-open - Testing Redis connection")
    ]
)

# Redis configuration from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))

# Create connection pool (reusable across requests)
_redis_pool = None


def get_redis_pool() -> ConnectionPool:
    """
    Get or create Redis connection pool.
    
    Returns:
        Redis connection pool
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = ConnectionPool.from_url(
            REDIS_URL,
            max_connections=REDIS_MAX_CONNECTIONS,
            decode_responses=True
        )
        logger.info(f"Created Redis connection pool: {REDIS_URL}")
    return _redis_pool


def get_redis_client() -> Redis:
    """
    Get a Redis client from the connection pool.
    
    Returns:
        Redis client instance
    """
    return Redis(connection_pool=get_redis_pool())


class RedisCache:
    """
    Redis caching utilities.
    """
    
    def __init__(self):
        self.client = get_redis_client()
    
    @redis_circuit_breaker
    def get(self, key: str) -> Optional[str]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
            
        Raises:
            pybreaker.CircuitBreakerError: If circuit is open (Redis unavailable)
        """
        try:
            return self.client.get(key)
        except Exception as e:
            logger.error(f"Redis GET failed for key {key}: {e}")
            return None
    
    @redis_circuit_breaker
    def set(self, key: str, value: str, ttl: int = 3600) -> bool:
        """
        Set value in cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (default: 1 hour)
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            pybreaker.CircuitBreakerError: If circuit is open (Redis unavailable)
        """
        try:
            return self.client.setex(key, ttl, value)
        except Exception as e:
            logger.error(f"Redis SET failed for key {key}: {e}")
            return False
    
    @redis_circuit_breaker
    def delete(self, key: str) -> bool:
        """
        Delete key from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            pybreaker.CircuitBreakerError: If circuit is open (Redis unavailable)
        """
        try:
            return self.client.delete(key) > 0
        except Exception as e:
            logger.error(f"Redis DELETE failed for key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis EXISTS failed for key {key}: {e}")
            return False
    
    def set_json(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """
        Set JSON-serializable value in cache.
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON-serialized)
            ttl: Time-to-live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            json_value = json.dumps(value)
            return self.set(key, json_value, ttl)
        except Exception as e:
            logger.error(f"Redis SET_JSON failed for key {key}: {e}")
            return False
    
    def get_json(self, key: str) -> Optional[Any]:
        """
        Get JSON value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Deserialized JSON value or None
        """
        try:
            value = self.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis GET_JSON failed for key {key}: {e}")
            return None


class RateLimiter:
    """
    Sliding window rate limiter using Redis.
    """
    
    def __init__(self, requests_per_minute: int = 60):
        self.client = get_redis_client()
        self.requests_per_minute = requests_per_minute
        self.window_size = 60  # seconds
    
    @redis_circuit_breaker
    def is_allowed(self, user_id: int, endpoint: str = "api") -> bool:
        """
        Check if request is allowed under rate limit.
        
        Uses sliding window algorithm with Redis sorted sets.
        
        Args:
            user_id: User ID for rate limiting
            endpoint: Endpoint identifier (for separate limits per endpoint)
            
        Returns:
            True if request is allowed, False if rate limit exceeded
            
        Raises:
            pybreaker.CircuitBreakerError: If circuit is open (Redis unavailable)
        """
        try:
            import time
            
            key = f"rate_limit:{endpoint}:{user_id}"
            now = time.time()
            window_start = now - self.window_size
            
            # Remove old entries outside window
            self.client.zremrangebyscore(key, 0, window_start)
            
            # Count requests in current window
            request_count = self.client.zcard(key)
            
            if request_count >= self.requests_per_minute:
                return False
            
            # Add current request
            self.client.zadd(key, {str(now): now})
            
            # Set expiration on key (cleanup)
            self.client.expire(key, self.window_size)
            
            return True
            
        except Exception as e:
            logger.error(f"Rate limiter check failed for user {user_id}: {e}")
            # Fail open (allow request) to avoid blocking on Redis failures
            return True
    
    def get_remaining(self, user_id: int, endpoint: str = "api") -> int:
        """
        Get remaining requests in current window.
        
        Args:
            user_id: User ID
            endpoint: Endpoint identifier
            
        Returns:
            Number of remaining requests
        """
        try:
            import time
            
            key = f"rate_limit:{endpoint}:{user_id}"
            now = time.time()
            window_start = now - self.window_size
            
            # Remove old entries
            self.client.zremrangebyscore(key, 0, window_start)
            
            # Count current requests
            request_count = self.client.zcard(key)
            
            return max(0, self.requests_per_minute - request_count)
            
        except Exception as e:
            logger.error(f"Rate limiter get_remaining failed for user {user_id}: {e}")
            return self.requests_per_minute


class MessageDeduplicator:
    """
    Message deduplication cache (24-hour window).
    """
    
    def __init__(self, ttl: int = 86400):  # 24 hours
        self.client = get_redis_client()
        self.ttl = ttl
    
    @redis_circuit_breaker
    def is_duplicate(self, message_id: str) -> bool:
        """
        Check if message ID has been seen before.
        
        Args:
            message_id: Message UUID
            
        Returns:
            True if duplicate, False if new
            
        Raises:
            pybreaker.CircuitBreakerError: If circuit is open (Redis unavailable)
        """
        try:
            key = f"message:dedup:{message_id}"
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Deduplication check failed for message {message_id}: {e}")
            return False
    
    @redis_circuit_breaker
    def mark_seen(self, message_id: str) -> bool:
        """
        Mark message as seen (add to deduplication cache).
        
        Args:
            message_id: Message UUID
            
        Returns:
            True if successful
            
        Raises:
            pybreaker.CircuitBreakerError: If circuit is open (Redis unavailable)
        """
        try:
            key = f"message:dedup:{message_id}"
            return self.client.setex(key, self.ttl, "1")
        except Exception as e:
            logger.error(f"Deduplication mark failed for message {message_id}: {e}")
            return False


# Global instances (lazy-initialized)
_cache = None
_rate_limiter = None
_deduplicator = None


def get_cache() -> RedisCache:
    """Get global cache instance."""
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        requests_per_minute = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60"))
        _rate_limiter = RateLimiter(requests_per_minute=requests_per_minute)
    return _rate_limiter


def get_deduplicator() -> MessageDeduplicator:
    """Get global message deduplicator instance."""
    global _deduplicator
    if _deduplicator is None:
        _deduplicator = MessageDeduplicator()
    return _deduplicator
