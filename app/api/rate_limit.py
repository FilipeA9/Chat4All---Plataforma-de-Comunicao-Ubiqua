"""
Rate limiting middleware for FastAPI.
Implements sliding window rate limiting using Redis with audit logging (T017).
"""
import logging
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from services.redis_client import get_rate_limiter
from api.dependencies import get_optional_user
from sqlalchemy.orm import Session
from db.database import SessionLocal
from core.audit_logger import audit_logger

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis sliding window algorithm.
    
    Applies rate limits to state-changing endpoints (POST, PUT, PATCH, DELETE).
    Rate limit: 60 requests per minute per user (configurable via env).
    """
    
    # Endpoints exempt from rate limiting
    EXEMPT_PATHS = {
        "/health",
        "/ready",
        "/metrics",
        "/metrics/basic",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/auth/token",  # Login should have separate rate limit
    }
    
    # HTTP methods subject to rate limiting
    RATE_LIMITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    
    async def dispatch(self, request: Request, call_next):
        """
        Apply rate limiting to requests.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler
            
        Returns:
            Response or 429 Too Many Requests
        """
        # Skip rate limiting for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)
        
        # Skip rate limiting for read-only methods
        if request.method not in self.RATE_LIMITED_METHODS:
            return await call_next(request)
        
        # Extract user from Authorization header
        user = None
        try:
            db = SessionLocal()
            try:
                authorization = request.headers.get("Authorization")
                if authorization:
                    from api.dependencies import get_optional_user as get_user_sync
                    from core.security import decode_access_token
                    from db.repository import Repository
                    
                    if authorization.startswith("Bearer "):
                        token = authorization.replace("Bearer ", "")
                        payload = decode_access_token(token)
                        
                        if payload and "user_id" in payload:
                            repository = Repository(db)
                            user = repository.get_user_by_id(payload["user_id"])
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to extract user for rate limiting: {e}")
        
        # If no user, apply rate limit by IP address
        if not user:
            identifier = request.client.host if request.client else "unknown"
            rate_limit_key = f"ip:{identifier}"
        else:
            rate_limit_key = f"user:{user.id}"
        
        # Check rate limit
        rate_limiter = get_rate_limiter()
        
        # Use endpoint path as rate limit scope
        endpoint = request.url.path
        
        try:
            # Check if request is allowed
            user_id = user.id if user else hash(rate_limit_key)
            allowed = rate_limiter.is_allowed(user_id, endpoint)
            
            if not allowed:
                # Get remaining requests for Retry-After header
                remaining = rate_limiter.get_remaining(user_id, endpoint)
                
                logger.warning(
                    f"Rate limit exceeded for {rate_limit_key} on {endpoint} "
                    f"(method={request.method})"
                )
                
                # Audit log: Rate limit exceeded (T017)
                ip_address = request.client.host if request.client else "unknown"
                request_id = getattr(request.state, 'request_id', 'unknown')
                audit_logger.log_rate_limit_exceeded(
                    user_id=str(user.id) if user else None,
                    ip_address=ip_address,
                    request_id=request_id,
                    endpoint=endpoint,
                    limit=rate_limiter.requests_per_minute,
                    window_seconds=60
                )
                
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later.",
                    headers={
                        "Retry-After": "60",  # seconds
                        "X-RateLimit-Limit": str(rate_limiter.requests_per_minute),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": "60"
                    }
                )
            
            # Add rate limit headers to successful responses
            response = await call_next(request)
            
            remaining = rate_limiter.get_remaining(user_id, endpoint)
            response.headers["X-RateLimit-Limit"] = str(rate_limiter.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Rate limiting error: {e}")
            # Fail open (allow request) to avoid blocking on errors
            return await call_next(request)


def create_rate_limit_middleware():
    """
    Factory function to create rate limit middleware.
    
    Returns:
        RateLimitMiddleware instance
    """
    return RateLimitMiddleware
