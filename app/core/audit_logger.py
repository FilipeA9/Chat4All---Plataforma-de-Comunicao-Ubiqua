"""
Audit logging for security events.
Logs authentication failures, token revocation, rate limit violations,
and other security-critical events for compliance and forensics.
"""
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of security audit events."""
    # Authentication events
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    TOKEN_ISSUED = "token_issued"
    TOKEN_REFRESH = "token_refresh"
    TOKEN_REVOKED = "token_revoked"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_INVALID = "token_invalid"
    
    # Authorization events
    AUTHZ_DENIED = "authorization_denied"
    AUTHZ_GRANTED = "authorization_granted"
    
    # Rate limiting events
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    RATE_LIMIT_WARNING = "rate_limit_warning"
    
    # Access events
    SENSITIVE_DATA_ACCESS = "sensitive_data_access"
    ADMIN_ACTION = "admin_action"
    
    # Security violations
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    BRUTE_FORCE_DETECTED = "brute_force_detected"
    INVALID_TOKEN_SIGNATURE = "invalid_token_signature"


class AuditLogger:
    """
    Security audit logger for compliance and forensics.
    
    All audit events are logged with:
    - Timestamp (ISO 8601)
    - Event type
    - User/client identifier
    - Source IP address
    - Request ID (for correlation)
    - Additional context metadata
    """
    
    @staticmethod
    def log_event(
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        client_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        request_id: Optional[str] = None,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Log a security audit event.
        
        Args:
            event_type: Type of security event
            user_id: User identifier (if available)
            client_id: OAuth client_id (if available)
            ip_address: Source IP address
            request_id: Request correlation ID
            success: Whether the operation succeeded
            metadata: Additional context (e.g., endpoint, scope, resource)
            error_message: Error message for failed operations
        """
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type.value,
            "success": success,
            "user_id": user_id,
            "client_id": client_id,
            "ip_address": ip_address,
            "request_id": request_id,
            "metadata": metadata or {},
            "error_message": error_message
        }
        
        # Log at appropriate level
        log_level = logging.INFO if success else logging.WARNING
        if event_type in [
            AuditEventType.SUSPICIOUS_ACTIVITY,
            AuditEventType.BRUTE_FORCE_DETECTED,
            AuditEventType.INVALID_TOKEN_SIGNATURE
        ]:
            log_level = logging.ERROR
        
        logger.log(
            log_level,
            f"AUDIT: {event_type.value} | "
            f"user={user_id} | client={client_id} | ip={ip_address} | "
            f"success={success} | {json.dumps(audit_entry)}"
        )
    
    @staticmethod
    def log_auth_success(
        user_id: str,
        client_id: str,
        ip_address: str,
        request_id: str,
        grant_type: str = "client_credentials"
    ) -> None:
        """Log successful authentication."""
        AuditLogger.log_event(
            event_type=AuditEventType.AUTH_SUCCESS,
            user_id=user_id,
            client_id=client_id,
            ip_address=ip_address,
            request_id=request_id,
            success=True,
            metadata={"grant_type": grant_type}
        )
    
    @staticmethod
    def log_auth_failure(
        client_id: Optional[str],
        ip_address: str,
        request_id: str,
        reason: str,
        grant_type: str = "client_credentials"
    ) -> None:
        """Log failed authentication attempt."""
        AuditLogger.log_event(
            event_type=AuditEventType.AUTH_FAILURE,
            client_id=client_id,
            ip_address=ip_address,
            request_id=request_id,
            success=False,
            metadata={"grant_type": grant_type},
            error_message=reason
        )
    
    @staticmethod
    def log_token_issued(
        user_id: str,
        client_id: str,
        ip_address: str,
        request_id: str,
        token_type: str = "access_token",
        expires_in: int = 900
    ) -> None:
        """Log token issuance."""
        AuditLogger.log_event(
            event_type=AuditEventType.TOKEN_ISSUED,
            user_id=user_id,
            client_id=client_id,
            ip_address=ip_address,
            request_id=request_id,
            success=True,
            metadata={"token_type": token_type, "expires_in": expires_in}
        )
    
    @staticmethod
    def log_token_refresh(
        user_id: str,
        client_id: str,
        ip_address: str,
        request_id: str
    ) -> None:
        """Log token refresh."""
        AuditLogger.log_event(
            event_type=AuditEventType.TOKEN_REFRESH,
            user_id=user_id,
            client_id=client_id,
            ip_address=ip_address,
            request_id=request_id,
            success=True
        )
    
    @staticmethod
    def log_token_revoked(
        user_id: str,
        client_id: str,
        ip_address: str,
        request_id: str,
        token_type: str = "refresh_token"
    ) -> None:
        """Log token revocation."""
        AuditLogger.log_event(
            event_type=AuditEventType.TOKEN_REVOKED,
            user_id=user_id,
            client_id=client_id,
            ip_address=ip_address,
            request_id=request_id,
            success=True,
            metadata={"token_type": token_type}
        )
    
    @staticmethod
    def log_token_invalid(
        ip_address: str,
        request_id: str,
        reason: str,
        endpoint: Optional[str] = None
    ) -> None:
        """Log invalid token usage attempt."""
        AuditLogger.log_event(
            event_type=AuditEventType.TOKEN_INVALID,
            ip_address=ip_address,
            request_id=request_id,
            success=False,
            metadata={"endpoint": endpoint},
            error_message=reason
        )
    
    @staticmethod
    def log_rate_limit_exceeded(
        user_id: Optional[str],
        ip_address: str,
        request_id: str,
        endpoint: str,
        limit: int,
        window_seconds: int
    ) -> None:
        """Log rate limit violation."""
        AuditLogger.log_event(
            event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
            user_id=user_id,
            ip_address=ip_address,
            request_id=request_id,
            success=False,
            metadata={
                "endpoint": endpoint,
                "limit": limit,
                "window_seconds": window_seconds
            },
            error_message=f"Rate limit exceeded: {limit} requests per {window_seconds}s"
        )
    
    @staticmethod
    def log_authorization_denied(
        user_id: str,
        ip_address: str,
        request_id: str,
        resource: str,
        action: str,
        reason: str
    ) -> None:
        """Log authorization denial."""
        AuditLogger.log_event(
            event_type=AuditEventType.AUTHZ_DENIED,
            user_id=user_id,
            ip_address=ip_address,
            request_id=request_id,
            success=False,
            metadata={"resource": resource, "action": action},
            error_message=reason
        )
    
    @staticmethod
    def log_suspicious_activity(
        user_id: Optional[str],
        ip_address: str,
        request_id: str,
        activity_type: str,
        details: str
    ) -> None:
        """Log suspicious security activity."""
        AuditLogger.log_event(
            event_type=AuditEventType.SUSPICIOUS_ACTIVITY,
            user_id=user_id,
            ip_address=ip_address,
            request_id=request_id,
            success=False,
            metadata={"activity_type": activity_type},
            error_message=details
        )


# Global audit logger instance
audit_logger = AuditLogger()
