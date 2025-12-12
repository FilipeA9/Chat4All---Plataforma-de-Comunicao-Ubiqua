"""
Security utilities for password hashing, JWT tokens, and OAuth 2.0.
Uses bcrypt for secure password hashing.
Uses python-jose for JWT token generation and validation.
"""
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import bcrypt
from jose import jwt, JWTError
from core.config import settings


# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "changeme-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")  # Use RS256 in production with RSA keys
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password to hash
        
    Returns:
        Hashed password as a string
    """
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    
    Args:
        plain_password: Plain text password to verify
        hashed_password: Previously hashed password
        
    Returns:
        True if password matches, False otherwise
    """
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(user_id: int, scope: str = "read write", tenant_id: str = "default") -> Dict[str, Any]:
    """
    Create a JWT access token (OAuth 2.0 Client Credentials flow).
    
    Args:
        user_id: User ID to encode in the token
        scope: OAuth 2.0 scopes (space-separated)
        tenant_id: Tenant identifier (single-tenant deployment uses "default")
        
    Returns:
        Dictionary with token, token_hash, expires_at, issued_at
    """
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "type": "access"
    }
    
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    return {
        "token": token,
        "token_hash": token_hash,
        "expires_at": expires_at,
        "issued_at": now
    }


def create_refresh_token(user_id: int) -> Dict[str, Any]:
    """
    Create an opaque refresh token (30 day expiration).
    
    Args:
        user_id: User ID associated with the token
        
    Returns:
        Dictionary with token, token_hash, expires_at, issued_at
    """
    now = datetime.utcnow()
    expires_at = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Generate cryptographically secure random token (256 bits = 64 hex chars)
    token = secrets.token_hex(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    return {
        "token": token,
        "token_hash": token_hash,
        "expires_at": expires_at,
        "issued_at": now
    }


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT access token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload if valid, None if invalid or expired
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def hash_token(token: str) -> str:
    """
    Generate SHA-256 hash of a token for storage/comparison.
    
    Args:
        token: Token string (JWT or opaque)
        
    Returns:
        SHA-256 hash as hex string
    """
    return hashlib.sha256(token.encode()).hexdigest()
