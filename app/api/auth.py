"""
OAuth 2.0 authentication endpoints.
Implements Client Credentials flow with JWT access tokens and refresh tokens.
Includes comprehensive audit logging for security events (T017).
"""
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from api.dependencies import get_db, get_current_user
from db.models import User, AccessToken, RefreshToken
from db.repository import Repository
from core.security import (
    create_access_token, 
    create_refresh_token,
    decode_access_token,
    hash_token,
    verify_password
)
from core.audit_logger import audit_logger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# Request/Response Models
class TokenRequest(BaseModel):
    """OAuth 2.0 token request (Client Credentials)."""
    username: str
    password: str
    grant_type: str = "password"


class TokenResponse(BaseModel):
    """OAuth 2.0 token response."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds
    refresh_token: str
    scope: str = "read write"


class RefreshRequest(BaseModel):
    """OAuth 2.0 refresh token request."""
    refresh_token: str
    grant_type: str = "refresh_token"


class RevokeRequest(BaseModel):
    """Token revocation request."""
    token: str
    token_type_hint: str = "refresh_token"  # or "access_token"


class TokenIntrospectResponse(BaseModel):
    """Token introspection response."""
    active: bool
    scope: str = None
    client_id: str = None
    username: str = None
    token_type: str = None
    exp: int = None
    iat: int = None
    sub: str = None


# Endpoints
@router.post("/token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def issue_token(request_body: TokenRequest, request: Request, db: Session = Depends(get_db)):
    """
    Issue OAuth 2.0 access and refresh tokens.
    
    Implements OAuth 2.0 Client Credentials flow with password grant.
    Returns a JWT access token (15min expiration) and opaque refresh token (30 days).
    
    Args:
        request_body: Username, password, and grant_type
        request: FastAPI Request for IP and request_id
        db: Database session
        
    Returns:
        TokenResponse with access_token, refresh_token, and expiration info
        
    Raises:
        HTTPException: 401 if credentials are invalid
        
    Example:
        POST /auth/token
        {
            "username": "user1",
            "password": "password123",
            "grant_type": "client_credentials"
        }
    """
    repository = Repository(db)
    
    # Extract request metadata for audit logging
    ip_address = request.client.host if request.client else "unknown"
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    # Validate user credentials
    user = repository.get_user_by_username(request_body.username)
    if not user or not verify_password(request_body.password, user.password):
        logger.warning(f"Failed authentication attempt for username: {request_body.username}")
        
        # Audit log: Authentication failure (T017)
        audit_logger.log_auth_failure(
            client_id=request_body.username,
            ip_address=ip_address,
            request_id=request_id,
            reason="Invalid username or password",
            grant_type=request_body.grant_type
        )
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Generate access token (JWT, 15 min)
    access_data = create_access_token(user.id, scope="read write", tenant_id="default")
    
    # Generate refresh token (opaque, 30 days)
    refresh_data = create_refresh_token(user.id)
    
    # Store tokens in database
    try:
        # Store access token
        access_token_record = AccessToken(
            user_id=user.id,
            token_hash=access_data["token_hash"],
            scope="read write",
            issued_at=access_data["issued_at"],
            expires_at=access_data["expires_at"],
            revoked=False
        )
        db.add(access_token_record)
        
        # Store refresh token
        refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=refresh_data["token_hash"],
            issued_at=refresh_data["issued_at"],
            expires_at=refresh_data["expires_at"],
            revoked=False
        )
        db.add(refresh_token_record)
        
        db.commit()
        
        logger.info(f"Issued tokens for user: {user.username} (user_id={user.id})")
        
        # Audit log: Authentication success (T017)
        audit_logger.log_auth_success(
            user_id=str(user.id),
            client_id=user.username,
            ip_address=ip_address,
            request_id=request_id,
            grant_type=request_body.grant_type
        )
        
        # Audit log: Token issued (T017)
        expires_in = int((access_data["expires_at"] - access_data["issued_at"]).total_seconds())
        audit_logger.log_token_issued(
            user_id=str(user.id),
            client_id=user.username,
            ip_address=ip_address,
            request_id=request_id,
            token_type="access_token",
            expires_in=expires_in
        )
        
        return TokenResponse(
            access_token=access_data["token"],
            token_type="Bearer",
            expires_in=expires_in,
            refresh_token=refresh_data["token"],
            scope="read write"
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to store tokens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to issue tokens"
        )


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def refresh_access_token(request_body: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    """
    Refresh an expired access token using a valid refresh token.
    
    Args:
        request_body: Refresh token and grant_type
        request: FastAPI Request for IP and request_id
        db: Database session
        
    Returns:
        TokenResponse with new access_token and same refresh_token
        
    Raises:
        HTTPException: 401 if refresh token is invalid, expired, or revoked
        
    Example:
        POST /auth/refresh
        {
            "refresh_token": "abc123...",
            "grant_type": "refresh_token"
        }
    """
    # Extract request metadata for audit logging
    ip_address = request.client.host if request.client else "unknown"
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    refresh_token_hash = hash_token(request_body.refresh_token)
    
    # Find refresh token in database
    refresh_record = db.query(RefreshToken).filter(
        RefreshToken.token_hash == refresh_token_hash
    ).first()
    
    if not refresh_record:
        # Audit log: Invalid token (T017)
        audit_logger.log_token_invalid(
            ip_address=ip_address,
            request_id=request_id,
            reason="Invalid refresh token",
            endpoint="/auth/refresh"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Check if revoked
    if refresh_record.revoked:
        logger.warning(f"Attempted use of revoked refresh token for user_id={refresh_record.user_id}")
        
        # Audit log: Invalid token (T017)
        audit_logger.log_token_invalid(
            ip_address=ip_address,
            request_id=request_id,
            reason="Refresh token has been revoked",
            endpoint="/auth/refresh"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Check if expired
    if datetime.utcnow() > refresh_record.expires_at:
        logger.warning(f"Expired refresh token used for user_id={refresh_record.user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Generate new access token
    access_data = create_access_token(refresh_record.user_id, scope="read write", tenant_id="default")
    
    # Store new access token
    try:
        access_token_record = AccessToken(
            user_id=refresh_record.user_id,
            token_hash=access_data["token_hash"],
            scope="read write",
            issued_at=access_data["issued_at"],
            expires_at=access_data["expires_at"],
            revoked=False
        )
        db.add(access_token_record)
        
        # Update last_used_at on refresh token
        refresh_record.last_used_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Refreshed access token for user_id={refresh_record.user_id}")
        
        # Get user for audit logging
        repository = Repository(db)
        user = repository.get_user_by_id(refresh_record.user_id)
        
        # Audit log: Token refresh (T017)
        audit_logger.log_token_refresh(
            user_id=str(refresh_record.user_id),
            client_id=user.username if user else "unknown",
            ip_address=ip_address,
            request_id=request_id
        )
        
        expires_in = int((access_data["expires_at"] - access_data["issued_at"]).total_seconds())
        
        return TokenResponse(
            access_token=access_data["token"],
            token_type="Bearer",
            expires_in=expires_in,
            refresh_token=request_body.refresh_token,  # Return same refresh token
            scope="read write"
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to refresh token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to refresh token"
        )


@router.post("/revoke", status_code=status.HTTP_200_OK)
def revoke_token(request_body: RevokeRequest, request: Request, db: Session = Depends(get_db)):
    """
    Revoke an access or refresh token (logout functionality).
    
    Args:
        request_body: Token to revoke and token_type_hint
        request: FastAPI Request for IP and request_id
        db: Database session
        
    Returns:
        Success message
        
    Example:
        POST /auth/revoke
        {
            "token": "abc123...",
            "token_type_hint": "refresh_token"
        }
    """
    # Extract request metadata for audit logging
    ip_address = request.client.host if request.client else "unknown"
    request_id = getattr(request.state, 'request_id', 'unknown')
    repository = Repository(db)
    
    token_hash_value = hash_token(request_body.token)
    
    try:
        # Try to revoke as refresh token first (most common case)
        if request_body.token_type_hint == "refresh_token":
            refresh_record = db.query(RefreshToken).filter(
                RefreshToken.token_hash == token_hash_value
            ).first()
            
            if refresh_record and not refresh_record.revoked:
                refresh_record.revoked = True
                refresh_record.revoked_at = datetime.utcnow()
                db.commit()
                logger.info(f"Revoked refresh token for user_id={refresh_record.user_id}")
                
                # Get user for audit logging
                user = repository.get_user_by_id(refresh_record.user_id)
                
                # Audit log: Token revoked (T017)
                audit_logger.log_token_revoked(
                    user_id=str(refresh_record.user_id),
                    client_id=user.username if user else "unknown",
                    ip_address=ip_address,
                    request_id=request_id,
                    token_type="refresh_token"
                )
                
                return {"message": "Token revoked successfully"}
        
        # Try to revoke as access token
        access_record = db.query(AccessToken).filter(
            AccessToken.token_hash == token_hash_value
        ).first()
        
        if access_record and not access_record.revoked:
            access_record.revoked = True
            access_record.revoked_at = datetime.utcnow()
            db.commit()
            logger.info(f"Revoked access token for user_id={access_record.user_id}")
            
            # Get user for audit logging
            user = repository.get_user_by_id(access_record.user_id)
            
            # Audit log: Token revoked (T017)
            audit_logger.log_token_revoked(
                user_id=str(access_record.user_id),
                client_id=user.username if user else "unknown",
                ip_address=ip_address,
                request_id=request_id,
                token_type="access_token"
            )
            
            return {"message": "Token revoked successfully"}
        
        # Token not found or already revoked (return success per OAuth 2.0 spec)
        return {"message": "Token revoked successfully"}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to revoke token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke token"
        )


@router.get("/me", status_code=status.HTTP_200_OK)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user information.
    
    Requires valid JWT access token in Authorization header.
    
    Args:
        current_user: Authenticated user (injected)
        
    Returns:
        User information
        
    Example:
        GET /auth/me
        Authorization: Bearer <jwt_token>
    """
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "created_at": current_user.created_at.isoformat()
    }
