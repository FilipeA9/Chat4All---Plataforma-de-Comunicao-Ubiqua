"""
Dependency injection functions for FastAPI.
Provides database sessions and authentication dependencies.
Enhanced with OAuth 2.0 JWT authentication.
"""
from typing import Generator, Optional
from datetime import datetime
from uuid import UUID
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.repository import Repository
from db.models import User, AccessToken
from core.security import decode_access_token, hash_token

security = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency that provides a database session.
    Automatically closes the session when request completes.
    
    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_legacy(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    LEGACY: Dependency that validates old UUID-based authentication token.
    Kept for backward compatibility. Will be deprecated in future versions.
    
    Args:
        credentials: HTTP Bearer token from Authorization header
        db: Database session
        
    Returns:
        Authenticated User object
        
    Raises:
        HTTPException: 401 if token is invalid or expired
    """
    try:
        token = UUID(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format"
        )
    
    repository = Repository(db)
    auth_session = repository.get_auth_session_by_token(token)
    
    if not auth_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    user = repository.get_user_by_id(auth_session.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    OAuth 2.0 JWT authentication dependency.
    Validates Bearer token (JWT), checks signature, expiration, and revocation.
    
    Args:
        credentials: HTTP Bearer token (JWT) from Authorization header
        db: Database session
        
    Returns:
        Authenticated User object
        
    Raises:
        HTTPException: 401 if token is invalid, expired, or revoked
    """
    token = credentials.credentials
    
    # Decode and validate JWT
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Check token revocation in database
    token_hash_value = hash_token(token)
    access_token = db.query(AccessToken).filter(
        AccessToken.token_hash == token_hash_value
    ).first()
    
    if access_token and access_token.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Get user
    repository = Repository(db)
    user = repository.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return user


def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Optional authentication dependency for endpoints that work with/without auth.
    
    Args:
        authorization: Optional Authorization header
        db: Database session
        
    Returns:
        User if authenticated, None otherwise
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    payload = decode_access_token(token)
    if not payload:
        return None
    
    user_id = payload.get("user_id")
    if not user_id:
        return None
    
    repository = Repository(db)
    return repository.get_user_by_id(user_id)


async def validate_websocket_token(token: str, db: Session) -> Optional[User]:
    """
    Validate JWT token for WebSocket connections.
    
    Used by WebSocket endpoint to authenticate users via query parameter token.
    Similar to get_current_user but returns None instead of raising exceptions
    to allow graceful connection rejection.
    
    Args:
        token: JWT token from WebSocket query parameter
        db: Database session
        
    Returns:
        User if token is valid, None otherwise
    """
    # Decode and validate JWT
    payload = decode_access_token(token)
    if not payload:
        return None
    
    # Check token type
    if payload.get("type") != "access":
        return None
    
    user_id = payload.get("user_id")
    if not user_id:
        return None
    
    # Check token revocation in database
    token_hash_value = hash_token(token)
    access_token = db.query(AccessToken).filter(
        AccessToken.token_hash == token_hash_value
    ).first()
    
    if access_token and access_token.revoked:
        return None
    
    # Get user
    repository = Repository(db)
    user = repository.get_user_by_id(user_id)
    return user
