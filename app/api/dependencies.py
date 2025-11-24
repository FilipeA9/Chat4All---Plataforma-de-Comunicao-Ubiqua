"""
Dependency injection functions for FastAPI.
Provides database sessions and authentication dependencies.
"""
from typing import Generator
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.repository import Repository
from db.models import User

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


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency that validates authentication token and returns current user.
    
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
