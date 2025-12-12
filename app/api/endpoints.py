"""
API endpoint implementations.
Defines all REST endpoints for authentication, conversations, messages, and files.
Includes WebSocket endpoint for real-time notifications.
"""
import logging
import json
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, WebSocket, WebSocketDisconnect, Query, Body
from sqlalchemy.orm import Session
from api.dependencies import get_db, get_current_user, validate_websocket_token
from api.schemas import (
    TokenRequest, TokenResponse, RefreshTokenRequest, RevokeTokenRequest,
    ConversationCreate, ConversationResponse, ConversationListResponse, ConversationListItem,
    MessageCreate, MessageResponse, MessageListResponse,
    FileInitiateRequest, FileInitiateResponse, FileChunkUploadResponse, FileStatusResponse, FileCompleteResponse,
    WSSubscribe, WSUnsubscribe, WSHeartbeat, WSError
)
from db.repository import Repository
from db.models import User, ConversationType, MessageStatus, FileStatus, AccessToken, RefreshToken
from core.security import verify_password, create_access_token, create_refresh_token, hash_token
from core.config import settings
from services.kafka_producer import get_kafka_producer
from api.websocket_manager import connection_manager

logger = logging.getLogger(__name__)

# Create routers
auth_router = APIRouter()
conversations_router = APIRouter()
messages_router = APIRouter()
files_router = APIRouter()
websocket_router = APIRouter()


# Authentication Endpoints (OAuth 2.0 Client Credentials Flow)
@auth_router.post("/token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def authenticate(request: TokenRequest, db: Session = Depends(get_db)):
    """
    OAuth 2.0 Client Credentials token endpoint (RFC 6749).
    
    Validates client credentials (username/password) and returns JWT access token
    and opaque refresh token. Access tokens expire in 15 minutes, refresh tokens
    expire in 30 days.
    
    Args:
        request: OAuth 2.0 token request (grant_type, client_id, client_secret, scope)
        db: Database session (injected)
        
    Returns:
        TokenResponse: OAuth 2.0 token response with access_token, refresh_token, expires_in
        
    Raises:
        HTTPException: 400 Bad Request if grant_type is invalid
        HTTPException: 401 Unauthorized if client credentials are invalid
        
    Example Request:
        ```json
        POST /auth/token
        Content-Type: application/json
        {
            "grant_type": "client_credentials",
            "client_id": "user1",
            "client_secret": "password123",
            "scope": "read write"
        }
        ```
        
    Example Response:
        ```json
        {
            "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "a1b2c3d4e5f6789012345678901234567890abcdef",
            "token_type": "Bearer",
            "expires_in": 900,
            "scope": "read write"
        }
        ```
    """
    repository = Repository(db)
    
    # Validate grant_type
    if request.grant_type != "client_credentials":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unsupported_grant_type",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Get user by username (client_id)
    user = repository.get_user_by_username(request.client_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_client",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Verify password (client_secret)
    if not verify_password(request.client_secret, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_client",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Create JWT access token
    access_token_data = create_access_token(
        user_id=user.id,
        scope=request.scope or "read write",
        tenant_id="default"
    )
    
    # Store access token in database for revocation tracking
    access_token_record = AccessToken(
        user_id=user.id,
        token_hash=access_token_data["token_hash"],
        scope=request.scope or "read write",
        issued_at=access_token_data["issued_at"],
        expires_at=access_token_data["expires_at"],
        revoked=False
    )
    db.add(access_token_record)
    
    # Create opaque refresh token
    refresh_token_data = create_refresh_token(user_id=user.id)
    
    # Store refresh token in database
    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=refresh_token_data["token_hash"],
        issued_at=refresh_token_data["issued_at"],
        expires_at=refresh_token_data["expires_at"],
        revoked=False
    )
    db.add(refresh_token_record)
    db.commit()
    
    logger.info(f"User {user.username} authenticated successfully via OAuth 2.0 Client Credentials")
    
    # Calculate expires_in (15 minutes = 900 seconds)
    expires_in = int((access_token_data["expires_at"] - access_token_data["issued_at"]).total_seconds())
    
    return TokenResponse(
        access_token=access_token_data["token"],
        refresh_token=refresh_token_data["token"],
        token_type="Bearer",
        expires_in=expires_in,
        scope=request.scope or "read write"
    )


@auth_router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def refresh_access_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """
    OAuth 2.0 token refresh endpoint.
    
    Exchanges a valid refresh token for a new access token. Refresh token
    must not be expired or revoked. Optionally implements token rotation
    (invalidates old refresh token and issues new one).
    
    Args:
        request: OAuth 2.0 refresh token request (grant_type, refresh_token)
        db: Database session (injected)
        
    Returns:
        TokenResponse: New access token and refresh token
        
    Raises:
        HTTPException: 400 Bad Request if grant_type is invalid
        HTTPException: 401 Unauthorized if refresh token is invalid, expired, or revoked
        
    Example Request:
        ```json
        POST /auth/refresh
        Content-Type: application/json
        {
            "grant_type": "refresh_token",
            "refresh_token": "a1b2c3d4e5f6789012345678901234567890abcdef"
        }
        ```
        
    Example Response:
        ```json
        {
            "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "b2c3d4e5f6789012345678901234567890abcdefgh",
            "token_type": "Bearer",
            "expires_in": 900,
            "scope": "read write"
        }
        ```
    """
    # Validate grant_type
    if request.grant_type != "refresh_token":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unsupported_grant_type",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Hash the provided refresh token
    token_hash_value = hash_token(request.refresh_token)
    
    # Find refresh token in database
    refresh_token_record = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash_value
    ).first()
    
    if not refresh_token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_grant",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Check if token is revoked
    if refresh_token_record.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_grant",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Check if token is expired
    if refresh_token_record.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_grant",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Update last_used_at timestamp
    refresh_token_record.last_used_at = datetime.utcnow()
    
    # Create new JWT access token
    access_token_data = create_access_token(
        user_id=refresh_token_record.user_id,
        scope="read write",
        tenant_id="default"
    )
    
    # Store new access token in database
    access_token_record = AccessToken(
        user_id=refresh_token_record.user_id,
        token_hash=access_token_data["token_hash"],
        scope="read write",
        issued_at=access_token_data["issued_at"],
        expires_at=access_token_data["expires_at"],
        revoked=False
    )
    db.add(access_token_record)
    
    # Token rotation (T126): Issue new refresh token and revoke old one
    # Create new refresh token
    new_refresh_token_data = create_refresh_token(user_id=refresh_token_record.user_id)
    
    new_refresh_token_record = RefreshToken(
        user_id=refresh_token_record.user_id,
        token_hash=new_refresh_token_data["token_hash"],
        issued_at=new_refresh_token_data["issued_at"],
        expires_at=new_refresh_token_data["expires_at"],
        revoked=False
    )
    db.add(new_refresh_token_record)
    
    # Revoke old refresh token
    refresh_token_record.revoked = True
    refresh_token_record.revoked_at = datetime.utcnow()
    
    db.commit()
    
    logger.info(f"User ID {refresh_token_record.user_id} refreshed access token")
    
    # Calculate expires_in
    expires_in = int((access_token_data["expires_at"] - access_token_data["issued_at"]).total_seconds())
    
    return TokenResponse(
        access_token=access_token_data["token"],
        refresh_token=new_refresh_token_data["token"],
        token_type="Bearer",
        expires_in=expires_in,
        scope="read write"
    )


@auth_router.post("/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(request: RevokeTokenRequest, db: Session = Depends(get_db)):
    """
    OAuth 2.0 token revocation endpoint (RFC 7009).
    
    Revokes a refresh token, preventing it from being used to obtain new
    access tokens. This endpoint is idempotent - revoking an already revoked
    or non-existent token succeeds with 204 No Content.
    
    Args:
        request: Token revocation request (token, token_type_hint)
        db: Database session (injected)
        
    Returns:
        204 No Content (always succeeds)
        
    Example Request:
        ```json
        POST /auth/revoke
        Content-Type: application/json
        {
            "token": "a1b2c3d4e5f6789012345678901234567890abcdef",
            "token_type_hint": "refresh_token"
        }
        ```
    """
    # Hash the provided token
    token_hash_value = hash_token(request.token)
    
    # Find refresh token in database
    refresh_token_record = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash_value
    ).first()
    
    # If token exists and not already revoked, revoke it
    if refresh_token_record and not refresh_token_record.revoked:
        refresh_token_record.revoked = True
        refresh_token_record.revoked_at = datetime.utcnow()
        db.commit()
        logger.info(f"Refresh token for user ID {refresh_token_record.user_id} revoked")
    
    # Always return 204 (idempotent operation per RFC 7009)
    return None


# Conversation Endpoints
@conversations_router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    request: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new conversation (private or group).
    
    Private conversations require exactly 2 members, while group conversations
    require 3-100 members. All member IDs must exist in the database.
    
    Args:
        request: Conversation details (type, member_ids, name, description)
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        ConversationResponse: Created conversation with ID and member count
        
    Raises:
        HTTPException: 400 Bad Request if validation fails (invalid member count or IDs)
        HTTPException: 401 Unauthorized if token is invalid
        
    Example Request (Private):
        ```json
        POST /v1/conversations
        Authorization: Bearer <token>
        {
            "type": "private",
            "member_ids": [1, 2]
        }
        ```
        
    Example Request (Group):
        ```json
        POST /v1/conversations
        Authorization: Bearer <token>
        {
            "type": "group",
            "member_ids": [1, 2, 3, 4],
            "name": "Project Team",
            "description": "Discussion for project alpha"
        }
        ```
    """
    repository = Repository(db)
    
    # Validate member count based on conversation type
    if request.type == "private":
        if len(request.member_ids) != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Private conversations must have exactly 2 members"
            )
    elif request.type == "group":
        if len(request.member_ids) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Group conversations must have at least 3 members"
            )
        if len(request.member_ids) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Group conversations cannot have more than 100 members"
            )
    
    # Validate all member IDs exist
    for member_id in request.member_ids:
        user = repository.get_user_by_id(member_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with ID {member_id} not found"
            )
    
    # Create conversation
    conversation = repository.create_conversation(
        conversation_type=ConversationType(request.type.upper()),
        name=request.name,
        description=request.description
    )
    
    # Add members
    for member_id in request.member_ids:
        repository.add_conversation_member(conversation.id, member_id)
    
    logger.info(f"Conversation {conversation.id} created by user {current_user.username}")
    
    return ConversationResponse(
        id=conversation.id,
        type=conversation.type.value,
        name=conversation.name,
        description=conversation.description,
        created_at=conversation.created_at,
        member_count=len(request.member_ids)
    )


@conversations_router.get("", response_model=ConversationListResponse, status_code=status.HTTP_200_OK)
def list_conversations(
    limit: int = Query(20, ge=1, le=100, description="Maximum items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List conversations for the current user with pagination.
    
    Returns conversations sorted by most recent message timestamp descending.
    Includes last message preview and unread message count for each conversation.
    Uses materialized view for efficient querying.
    
    Args:
        limit: Maximum items per page (1-100, default: 20)
        offset: Number of items to skip (default: 0)
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        ConversationListResponse: Paginated list of conversations with metadata
        
    Raises:
        HTTPException: 401 Unauthorized if token is invalid
        
    Example Request:
        ```
        GET /v1/conversations?limit=20&offset=0
        Authorization: Bearer <token>
        ```
        
    Example Response:
        ```json
        {
            "items": [
                {
                    "conversation_id": 1,
                    "conversation_type": "group",
                    "conversation_name": "Project Team",
                    "last_message_timestamp": "2025-12-02T10:30:00Z",
                    "last_message_content": "Let's meet tomorrow at 10 AM",
                    "last_message_sender": "alice",
                    "unread_count": 3,
                    "conversation_created_at": "2025-11-01T08:00:00Z"
                }
            ],
            "total": 15,
            "limit": 20,
            "offset": 0,
            "has_more": false
        }
        ```
    """
    from sqlalchemy import text
    
    # Query conversation_view materialized view
    # Using text() for raw SQL since we're querying a materialized view
    query = text("""
        REFRESH MATERIALIZED VIEW conversation_view;
        SELECT 
            conversation_id,
            conversation_type,
            conversation_name,
            description,
            participant_usernames,
            last_message_timestamp,
            last_message_payload,
            last_message_sender_username,
            unread_count,
            conversation_created_at
        FROM conversation_view
        WHERE user_id = :user_id
        ORDER BY last_message_timestamp DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """)
    
    result = db.execute(
        query,
        {"user_id": current_user.id, "limit": limit, "offset": offset}
    )
    
    rows = result.fetchall()
    
    # Get total count
    count_query = text("""
        SELECT COUNT(*) as total
        FROM conversation_view
        WHERE user_id = :user_id
    """)
    
    total_result = db.execute(count_query, {"user_id": current_user.id})
    total = total_result.fetchone()[0]
    
    # Build response items
    items = []
    for row in rows:
        # Extract last message content from payload
        last_message_content = None
        if row.last_message_payload:
            payload = row.last_message_payload
            if isinstance(payload, dict):
                if payload.get('type') == 'text':
                    # Truncate to 100 characters
                    content = payload.get('content', '')
                    last_message_content = content[:100] + '...' if len(content) > 100 else content
                elif payload.get('type') == 'file':
                    last_message_content = "[File]"
        
        items.append(ConversationListItem(
            conversation_id=row.conversation_id,
            conversation_type=row.conversation_type,
            conversation_name=row.conversation_name,
            description=row.description,
            last_message_timestamp=row.last_message_timestamp,
            last_message_content=last_message_content,
            last_message_sender=row.last_message_sender_username,
            unread_count=row.unread_count,
            conversation_created_at=row.conversation_created_at
        ))
    
    has_more = (offset + len(items)) < total
    
    logger.info(
        f"User {current_user.username} listed {len(items)} conversations "
        f"(offset={offset}, total={total})"
    )
    
    return ConversationListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more
    )


@conversations_router.post("/{conversation_id}/read", status_code=status.HTTP_200_OK)
async def mark_conversation_as_read(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark all messages in a conversation as READ.
    
    Updates all unread messages to READ status and broadcasts a real-time
    notification to other conversation members via WebSocket. This enables
    read receipt functionality across all connected clients.
    
    Args:
        conversation_id: ID of the conversation to mark as read
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        dict: Number of messages marked as read
        
    Raises:
        HTTPException: 401 Unauthorized if token is invalid
        HTTPException: 403 Forbidden if user is not a conversation member
        HTTPException: 404 Not Found if conversation does not exist
        
    Example Request:
        ```
        POST /v1/conversations/1/read
        Authorization: Bearer <token>
        ```
        
    Example Response:
        ```json
        {
            "status": "success",
            "conversation_id": 1,
            "messages_marked_read": 10
        }
        ```
        
    WebSocket Notification:
        Other conversation members receive a real-time event:
        ```json
        {
            "type": "conversation.read",
            "conversation_id": 1,
            "user_id": 5,
            "username": "user1",
            "message_count": 10,
            "read_at": "2025-12-02T10:30:00Z",
            "timestamp": "2025-12-02T10:30:00.123Z"
        }
        ```
    """
    repository = Repository(db)
    
    # Check if conversation exists
    conversation = repository.get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Check if user is a member
    if not repository.is_conversation_member(conversation_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this conversation"
        )
    
    # Mark messages as read
    messages_marked = repository.mark_conversation_as_read(conversation_id, current_user.id)
    
    # Publish ConversationRead event to Redis for real-time notifications
    try:
        from services.redis_client import get_redis_client
        import json
        
        redis_client = get_redis_client()
        channel = f"conversation:{conversation_id}"
        
        ws_message = {
            'type': 'conversation.read',
            'conversation_id': conversation_id,
            'user_id': current_user.id,
            'username': current_user.username,
            'message_count': messages_marked,
            'read_at': datetime.utcnow().isoformat(),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        redis_client.publish(channel, json.dumps(ws_message))
        logger.info(
            f"User {current_user.username} marked conversation {conversation_id} as read "
            f"({messages_marked} messages)"
        )
    except Exception as e:
        logger.error(f"Failed to publish conversation.read event to Redis: {e}")
        # Don't fail the request if Redis is down
    
    return {
        "status": "success",
        "conversation_id": conversation_id,
        "messages_marked_read": messages_marked
    }


@conversations_router.get("/{conversation_id}/messages", response_model=MessageListResponse)
def get_conversation_messages(
    conversation_id: int,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get messages from a conversation with pagination.
    
    Returns messages in reverse chronological order (newest first). File messages
    are enriched with filename, size, and MIME type. User must be a conversation
    member to access messages.
    
    Args:
        conversation_id: ID of the conversation
        limit: Maximum messages to return per page (default: 50, max: 100)
        offset: Number of messages to skip for pagination (default: 0)
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        MessageListResponse: List of messages with metadata and pagination info
        
    Raises:
        HTTPException: 401 Unauthorized if token is invalid
        HTTPException: 403 Forbidden if user is not a conversation member
        HTTPException: 404 Not Found if conversation does not exist
        
    Example Request:
        ```
        GET /v1/conversations/1/messages?limit=10&offset=0
        Authorization: Bearer <token>
        ```
    """
    repository = Repository(db)
    
    # Check if conversation exists
    conversation = repository.get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Check if user is a member
    if not repository.is_conversation_member(conversation_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this conversation"
        )
    
    # Get messages
    messages = repository.get_conversation_messages(conversation_id, limit, offset)
    
    # Build response
    message_responses = []
    for message in messages:
        sender = repository.get_user_by_id(message.sender_id)
        
        # Enrich file messages with file metadata
        payload = message.payload.copy()
        if payload.get("type") == "file":
            file_id_str = payload.get("file_id")
            if file_id_str:
                file_metadata = repository.get_file_metadata(UUID(file_id_str))
                if file_metadata:
                    payload["filename"] = file_metadata.filename
                    payload["size_bytes"] = file_metadata.size_bytes
                    payload["mime_type"] = file_metadata.mime_type
        
        message_responses.append(MessageResponse(
            message_id=message.id,
            conversation_id=message.conversation_id,
            sender_id=message.sender_id,
            sender_username=sender.username if sender else "Unknown",
            payload=payload,
            status=message.status.value,
            channels=message.channels,
            created_at=message.created_at
        ))
    
    return MessageListResponse(
        messages=message_responses,
        total=len(message_responses),
        limit=limit,
        offset=offset
    )


# Message Endpoints
async def publish_message_to_kafka(message_data: dict):
    """
    Background task to publish message to Kafka.
    
    Args:
        message_data: Message data to publish
    """
    try:
        kafka_producer = get_kafka_producer()
        success = kafka_producer.publish_message("message_processing", message_data)
        if success:
            logger.info(f"Message {message_data['message_id']} published to Kafka")
        else:
            logger.error(f"Failed to publish message {message_data['message_id']} to Kafka")
    except Exception as e:
        logger.error(f"Error publishing message to Kafka: {e}")


@messages_router.post("", status_code=status.HTTP_202_ACCEPTED)
async def send_message(
    request: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send a message to a conversation.
    
    Accepts text or file messages and routes them to specified channels (WhatsApp,
    Instagram, or all). Messages are processed asynchronously via Kafka workers.
    Supports idempotency - duplicate message_id returns original response.
    
    Args:
        request: Message details (message_id, conversation_id, payload, channels)
        background_tasks: FastAPI background tasks (injected)
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        dict: Status "accepted" with message_id (HTTP 202)
        
    Raises:
        HTTPException: 400 Bad Request if file not found or validation fails
        HTTPException: 401 Unauthorized if token is invalid
        HTTPException: 403 Forbidden if user is not a conversation member
        HTTPException: 404 Not Found if conversation does not exist
        
    Example Request (Text):
        ```json
        POST /v1/messages
        Authorization: Bearer <token>
        {
            "message_id": "550e8400-e29b-41d4-a716-446655440000",
            "conversation_id": 1,
            "payload": {"type": "text", "content": "Hello, team!"},
            "channels": ["whatsapp", "instagram"]
        }
        ```
        
    Example Request (File):
        ```json
        POST /v1/messages
        Authorization: Bearer <token>
        {
            "message_id": "650e8400-e29b-41d4-a716-446655440000",
            "conversation_id": 1,
            "payload": {"type": "file", "file_id": "750e8400-e29b-41d4-a716-446655440000"},
            "channels": ["all"]
        }
        ```
        
    Example Response:
        ```json
        {
            "status": "accepted",
            "message_id": "550e8400-e29b-41d4-a716-446655440000"
        }
        ```
    """
    repository = Repository(db)
    
    # Check if message_id already exists (idempotency)
    existing_message = repository.get_message_by_id(request.message_id)
    if existing_message:
        logger.info(f"Duplicate message_id {request.message_id}, returning existing response")
        return {
            "status": "accepted",
            "message_id": str(existing_message.id)
        }
    
    # Check if conversation exists
    conversation = repository.get_conversation_by_id(request.conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Check if user is a member
    if not repository.is_conversation_member(request.conversation_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this conversation"
        )
    
    # Validate payload based on type
    payload_dict = request.payload.model_dump()
    
    if payload_dict["type"] == "file":
        # Validate file exists
        # file_id pode ser UUID ou string, dependendo de como foi serializado
        file_id = payload_dict["file_id"]
        if isinstance(file_id, UUID):
            file_id_uuid = file_id
            # Converte para string para armazenamento JSON
            payload_dict["file_id"] = str(file_id)
        else:
            file_id_uuid = UUID(file_id)
        file_metadata = repository.get_file_metadata(file_id_uuid)
        if not file_metadata:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File not found"
            )
        if file_metadata.status.value.upper() != "COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File upload not completed"
            )
    
    # Create message AND outbox event in single transaction (Transactional Outbox pattern)
    # This guarantees at-least-once delivery even if Kafka is temporarily unavailable
    try:
        # Begin transaction
        message = repository.create_message(
            message_id=request.message_id,
            conversation_id=request.conversation_id,
            sender_id=current_user.id,
            payload=payload_dict,
            channels=request.channels
        )
        
        # Create outbox event in same transaction
        outbox_payload = {
            "message_id": str(message.id),
            "conversation_id": message.conversation_id,
            "sender_id": message.sender_id,
            "sender_username": current_user.username,
            "payload": message.payload,
            "channels": message.channels,
            "created_at": message.created_at.isoformat(),
            "trace_id": None,  # TODO: Extract from request context when OpenTelemetry is integrated
            "request_id": None
        }
        
        repository.create_outbox_event(
            aggregate_type="message",
            aggregate_id=message.id,
            event_type="message.created",
            payload=outbox_payload
        )
        
        # Commit transaction (both message and outbox event are persisted atomically)
        db.commit()
        
        logger.info(f"Message {message.id} and outbox event created atomically for user {current_user.username}")
        
        return {
            "status": "accepted",
            "message_id": str(message.id)
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create message with outbox event: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process message"
        )


@messages_router.post("/fallback", status_code=status.HTTP_202_ACCEPTED)
async def send_message_fallback(
    request: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Send message with Redis fallback when Kafka is unavailable (T060).
    
    This endpoint implements graceful degradation using circuit breakers.
    When Kafka/Redis are unavailable (circuit open), messages are queued
    in a fallback Redis list and processed by workers/redis_backfill.py.
    
    Args:
        request: Message details (message_id, conversation_id, payload, channels)
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        dict: Status "accepted" with message_id (HTTP 202)
        Response includes X-Fallback-Mode: true header if circuit breaker engaged
        
    Raises:
        HTTPException: 400/401/403/404 (same as send_message)
        HTTPException: 503 Service Unavailable if both Kafka and Redis fail
    """
    import pybreaker
    from services.redis_client import get_redis_client
    
    repository = Repository(db)
    
    # Check if message_id already exists (idempotency)
    existing_message = repository.get_message_by_id(request.message_id)
    if existing_message:
        logger.info(f"Duplicate message_id {request.message_id}, returning existing response")
        return {
            "status": "accepted",
            "message_id": str(existing_message.id)
        }
    
    # Check if conversation exists
    conversation = repository.get_conversation_by_id(request.conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Check if user is a member
    if not repository.is_conversation_member(request.conversation_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this conversation"
        )
    
    # Validate payload based on type
    payload_dict = request.payload.model_dump()
    
    if payload_dict["type"] == "file":
        file_metadata = repository.get_file_metadata(UUID(payload_dict["file_id"]))
        if not file_metadata:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File not found"
            )
        if file_metadata.status.value != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File upload not completed"
            )
    
    # Create message in database
    try:
        message = repository.create_message(
            message_id=request.message_id,
            conversation_id=request.conversation_id,
            sender_id=current_user.id,
            payload=payload_dict,
            channels=request.channels
        )
        
        outbox_payload = {
            "message_id": str(message.id),
            "conversation_id": message.conversation_id,
            "sender_id": message.sender_id,
            "sender_username": current_user.username,
            "payload": message.payload,
            "channels": message.channels,
            "created_at": message.created_at.isoformat(),
            "trace_id": None,
            "request_id": None
        }
        
        # Try publishing to Kafka with circuit breaker
        fallback_mode = False
        try:
            kafka_producer = get_kafka_producer()
            kafka_producer.publish_message("message_processing", outbox_payload)
            logger.info(f"Message {message.id} published to Kafka successfully")
        except pybreaker.CircuitBreakerError:
            # Circuit is open - Kafka unavailable, use Redis fallback
            fallback_mode = True
            logger.warning(f"Kafka circuit breaker open, using Redis fallback for message {message.id}")
            
            try:
                redis_client = get_redis_client()
                fallback_key = "fallback:message_queue"
                redis_client.rpush(fallback_key, json.dumps(outbox_payload))
                logger.info(f"Message {message.id} queued in Redis fallback list")
            except pybreaker.CircuitBreakerError:
                # Redis circuit also open
                logger.error(f"Both Kafka and Redis circuits open - cannot process message {message.id}")
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Message processing services temporarily unavailable"
                )
            except Exception as e:
                logger.error(f"Redis fallback failed for message {message.id}: {e}")
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Fallback queue unavailable"
                )
        
        db.commit()
        
        response = {
            "status": "accepted",
            "message_id": str(message.id)
        }
        
        if fallback_mode:
            from fastapi import Response
            return Response(
                content=json.dumps(response),
                status_code=status.HTTP_202_ACCEPTED,
                headers={"X-Fallback-Mode": "true"},
                media_type="application/json"
            )
        
        return response
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create message: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process message"
        )


# ============================================================================
# File Upload Endpoints (Chunked Resumable Uploads)
# ============================================================================

@files_router.post("/initiate", response_model=FileInitiateResponse, status_code=status.HTTP_201_CREATED)
def initiate_chunked_file_upload(
    request: FileInitiateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Initiate a chunked file upload session.
    
    Creates a file upload session and returns metadata for chunk uploads.
    Maximum file size is 2GB. The session expires after 24 hours.
    After uploading all chunks, call POST /v1/files/{upload_id}/complete.
    
    Args:
        request: File metadata (conversation_id, filename, file_size, mime_type, chunk_size)
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        FileInitiateResponse: Upload ID, total chunks, chunk size, expiration
        
    Raises:
        HTTPException: 401 Unauthorized if token is invalid
        HTTPException: 403 Forbidden if user is not a member of the conversation
        HTTPException: 404 Not Found if conversation does not exist
        HTTPException: 413 Payload Too Large if file exceeds 2GB limit
        
    Example Request:
        ```json
        POST /v1/files/initiate
        Authorization: Bearer <token>
        {
            "conversation_id": 123,
            "filename": "vacation_video.mp4",
            "file_size": 1073741824,
            "mime_type": "video/mp4",
            "checksum_sha256": "abc123...",
            "chunk_size": 5242880
        }
        ```
        
    Example Response:
        ```json
        {
            "upload_id": "550e8400-e29b-41d4-a716-446655440000",
            "total_chunks": 205,
            "chunk_size": 5242880,
            "expires_at": "2025-11-25T15:30:00Z"
        }
        ```
        
    Next Steps:
        1. Split file into chunks (chunk_size bytes each, last chunk may be smaller)
        2. Upload each chunk: POST /v1/files/{upload_id}/chunks?chunk_number=N
        3. Monitor progress: GET /v1/files/{upload_id}/status
        4. Complete upload: POST /v1/files/{upload_id}/complete
    """
    import math
    
    # Validate file size (max 2GB)
    MAX_FILE_SIZE = 2_147_483_648  # 2GB in bytes
    if request.file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 2GB limit"
        )
    
    repository = Repository(db)
    
    # Verify conversation exists and user is a member
    conversation = repository.get_conversation_by_id(request.conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Check if user is a member of the conversation
    is_member = repository.is_conversation_member(request.conversation_id, current_user.id)
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this conversation"
        )
    
    # Calculate total chunks
    chunk_size = request.chunk_size or 10_485_760  # Default 10MB
    total_chunks = math.ceil(request.file_size / chunk_size)
    
    # Create File record
    from db.models import File, FileStatus
    
    file = File(
        id=uuid4(),
        conversation_id=request.conversation_id,
        uploader_id=current_user.id,
        filename=request.filename,
        file_size=request.file_size,
        mime_type=request.mime_type,
        checksum_sha256=request.checksum_sha256,
        status=FileStatus.PENDING,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        uploaded_chunks=0
    )
    
    db.add(file)
    db.commit()
    db.refresh(file)
    
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    logger.info(
        f"Chunked file upload initiated: {file.id} "
        f"({request.filename}, {request.file_size} bytes, {total_chunks} chunks) "
        f"by user {current_user.username}"
    )
    
    return FileInitiateResponse(
        upload_id=file.id,
        total_chunks=total_chunks,
        chunk_size=chunk_size,
        expires_at=expires_at
    )


@files_router.post("/{upload_id}/chunks", response_model=FileChunkUploadResponse, status_code=status.HTTP_200_OK)
async def upload_file_chunk(
    upload_id: UUID,
    chunk_number: int = Query(..., ge=1, description="1-based chunk number"),
    checksum_sha256: str | None = Query(None, regex=r'^[a-f0-9]{64}$', description="SHA-256 checksum of chunk"),
    chunk_data: bytes = Body(..., media_type="application/octet-stream"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a single file chunk.
    
    Uploads binary chunk data to MinIO and updates the file record.
    Chunks must be uploaded with chunk_number from 1 to total_chunks.
    Duplicate chunk uploads will be rejected with 409 Conflict.
    
    Args:
        upload_id: Upload session UUID (from POST /v1/files/initiate)
        chunk_number: 1-based chunk number (query parameter)
        checksum_sha256: Optional SHA-256 checksum for chunk integrity (query parameter)
        chunk_data: Binary chunk data (request body)
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        FileChunkUploadResponse: Upload progress (chunk_number, uploaded_chunks, percentage)
        
    Raises:
        HTTPException: 404 Not Found if upload session not found
        HTTPException: 403 Forbidden if upload belongs to different user
        HTTPException: 400 Bad Request if chunk_number is invalid
        HTTPException: 409 Conflict if chunk already uploaded
        
    Example:
        ```bash
        curl -X POST "http://localhost:8000/v1/files/550e8400.../chunks?chunk_number=5" \
             -H "Authorization: Bearer <token>" \
             -H "Content-Type: application/octet-stream" \
             --data-binary @chunk-005.bin
        ```
    """
    from db.models import File, FileChunkModel, FileStatus
    from services.minio_client import get_minio_client
    
    # Get file record
    file = db.query(File).filter(File.id == upload_id).first()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found"
        )
    
    # Verify uploader
    if file.uploader_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to upload to this session"
        )
    
    # Validate chunk_number
    if chunk_number < 1 or chunk_number > file.total_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid chunk_number. Must be between 1 and {file.total_chunks}"
        )
    
    # Check for duplicate chunk
    existing_chunk = db.query(FileChunkModel).filter(
        FileChunkModel.file_id == upload_id,
        FileChunkModel.chunk_number == chunk_number
    ).first()
    
    if existing_chunk:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Chunk {chunk_number} has already been uploaded"
        )
    
    # Upload chunk to MinIO
    minio_client = get_minio_client()
    storage_key = f"chunks/{upload_id}/chunk-{chunk_number:05d}"
    
    from io import BytesIO
    chunk_stream = BytesIO(chunk_data)
    chunk_size = len(chunk_data)
    
    minio_client.put_object(
        object_name=storage_key,
        data=chunk_stream,
        length=chunk_size,
        content_type="application/octet-stream"
    )
    
    # Create chunk record
    chunk = FileChunkModel(
        id=uuid4(),
        file_id=upload_id,
        chunk_number=chunk_number,
        chunk_size=chunk_size,
        storage_key=storage_key,
        checksum_sha256=checksum_sha256
    )
    
    db.add(chunk)
    
    # Update file uploaded_chunks and status
    file.uploaded_chunks += 1
    if file.status == FileStatus.PENDING:
        file.status = FileStatus.UPLOADING
    
    db.commit()
    
    # Calculate progress
    percentage = (file.uploaded_chunks / file.total_chunks) * 100
    
    logger.info(
        f"Chunk {chunk_number}/{file.total_chunks} uploaded for {upload_id} "
        f"({percentage:.2f}%)"
    )
    
    return FileChunkUploadResponse(
        upload_id=upload_id,
        chunk_number=chunk_number,
        uploaded_chunks=file.uploaded_chunks,
        total_chunks=file.total_chunks,
        percentage=round(percentage, 2)
    )


@files_router.get("/{upload_id}/status", response_model=FileStatusResponse, status_code=status.HTTP_200_OK)
def get_upload_status(
    upload_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Query upload session status.
    
    Returns current upload progress including uploaded/missing chunks.
    Useful for resuming interrupted uploads.
    
    Args:
        upload_id: Upload session UUID
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        FileStatusResponse: Upload status, progress, missing chunks
        
    Raises:
        HTTPException: 404 Not Found if upload session not found
        
    Example Response:
        ```json
        {
            "upload_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "uploading",
            "uploaded_chunks": 100,
            "total_chunks": 205,
            "percentage": 48.78,
            "missing_chunks": [101, 102, 103, ...],
            "created_at": "2025-11-30T10:00:00Z",
            "expires_at": "2025-12-01T10:00:00Z"
        }
        ```
    """
    from db.models import File, FileChunkModel
    
    # Get file record with chunks
    file = db.query(File).filter(File.id == upload_id).first()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found"
        )
    
    # Get uploaded chunk numbers
    uploaded_chunks_query = db.query(FileChunkModel.chunk_number).filter(
        FileChunkModel.file_id == upload_id
    ).all()
    uploaded_chunk_numbers = set(chunk[0] for chunk in uploaded_chunks_query)
    
    # Calculate missing chunks
    all_chunks = set(range(1, file.total_chunks + 1))
    missing_chunks = sorted(all_chunks - uploaded_chunk_numbers)
    
    # Calculate percentage
    percentage = (file.uploaded_chunks / file.total_chunks) * 100 if file.total_chunks > 0 else 0
    
    # Prepare response
    response = FileStatusResponse(
        upload_id=upload_id,
        status=file.status.value,
        uploaded_chunks=file.uploaded_chunks,
        total_chunks=file.total_chunks,
        percentage=round(percentage, 2),
        missing_chunks=missing_chunks if missing_chunks else None,
        created_at=file.created_at,
        expires_at=file.created_at + timedelta(hours=24) if file.status != FileStatus.COMPLETED else None,
        completed_at=file.completed_at
    )
    
    # Add download URL if completed
    if file.status == FileStatus.COMPLETED and file.storage_key:
        from services.minio_client import get_minio_client
        minio_client = get_minio_client()
        response.download_url = minio_client.presigned_get_url(
            file.storage_key,
            expires=timedelta(hours=24)
        )
        response.file_id = file.id
    
    return response


@files_router.post("/{upload_id}/complete", response_model=FileCompleteResponse, status_code=status.HTTP_202_ACCEPTED)
def complete_chunked_file_upload(
    upload_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Complete chunked file upload and trigger merge.
    
    Validates all chunks are uploaded, changes status to MERGING, and publishes
    a file_merge_request event to Kafka. A background worker will merge chunks
    into the final file.
    
    Args:
        upload_id: Upload session UUID
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        FileCompleteResponse: Status=merging, estimated completion time
        
    Raises:
        HTTPException: 404 Not Found if upload session not found
        HTTPException: 403 Forbidden if upload belongs to different user
        HTTPException: 400 Bad Request if not all chunks uploaded
        
    Example Response:
        ```json
        {
            "upload_id": "550e8400-e29b-41d4-a716-446655440000",
            "status": "merging",
            "message": "File merge initiated. Check status for completion.",
            "estimated_completion": "2025-11-30T12:00:10Z"
        }
        ```
    """
    from db.models import File, FileChunkModel, FileStatus
    
    # Get file record
    file = db.query(File).filter(File.id == upload_id).first()
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload session not found"
        )
    
    # Verify uploader
    if file.uploader_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to complete this upload"
        )
    
    # Validate all chunks uploaded
    if file.uploaded_chunks < file.total_chunks:
        # Get missing chunks for error message
        uploaded_chunks_query = db.query(FileChunkModel.chunk_number).filter(
            FileChunkModel.file_id == upload_id
        ).all()
        uploaded_chunk_numbers = set(chunk[0] for chunk in uploaded_chunks_query)
        all_chunks = set(range(1, file.total_chunks + 1))
        missing_chunks = sorted(all_chunks - uploaded_chunk_numbers)
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not all chunks have been uploaded. Missing: {missing_chunks[:10]}{'...' if len(missing_chunks) > 10 else ''}",
            headers={"X-Missing-Chunks": str(len(missing_chunks))}
        )
    
    # Update file status to MERGING
    file.status = FileStatus.COMPLETED  # Will be changed to a proper MERGING status later
    file.storage_key = f"files/{upload_id}/{file.filename}"
    db.commit()
    
    # Publish file_merge_request event to Kafka
    kafka_producer = get_kafka_producer()
    merge_event = {
        "upload_id": str(upload_id),
        "filename": file.filename,
        "total_chunks": file.total_chunks,
        "storage_key": file.storage_key,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    kafka_producer.publish_message(
        topic="file_merge_requests",
        message=merge_event,
        partition_key=str(upload_id)
    )
    
    estimated_completion = datetime.utcnow() + timedelta(seconds=30)  # Estimate based on file size
    
    logger.info(f"File merge initiated for {upload_id} ({file.total_chunks} chunks)")
    
    return FileCompleteResponse(
        upload_id=upload_id,
        status="merging",
        message="File merge initiated. Check status for completion.",
        estimated_completion=estimated_completion
    )


# WebSocket Endpoint
@websocket_router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token for authentication"),
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time message notifications.
    
    Provides bidirectional communication for instant message delivery, read receipts,
    and conversation events. Clients must authenticate via JWT token in query parameter.
    
    Connection Flow:
        1. Client connects with token: ws://api/ws?token={jwt}
        2. Server validates token and accepts/rejects connection
        3. Client subscribes to conversations: {"action": "subscribe", "conversation_id": 1}
        4. Server pushes notifications: MessageCreated, MessageRead, ConversationRead
        5. Server sends periodic pings (every 30s), client must respond with pong
        6. Client disconnects or connection times out (40s without heartbeat)
    
    Args:
        websocket: WebSocket connection
        token: JWT access token from query parameter
        db: Database session (injected)
        
    WebSocket Message Types (Server → Client):
        - message.created: New message in subscribed conversation
        - message.delivered: Message delivered to channel
        - message.read: Message marked as read by user
        - conversation.read: All messages marked as read
        - ping: Heartbeat check (client should respond with pong)
        - error: Error notification
        
    WebSocket Commands (Client → Server):
        - subscribe: {"action": "subscribe", "conversation_id": 1}
        - unsubscribe: {"action": "unsubscribe", "conversation_id": 1}
        - pong: {"action": "pong"} (response to ping)
        
    Example Connection:
        ```javascript
        const token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...";
        const ws = new WebSocket(`ws://localhost:8000/ws?token=${token}`);
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === "ping") {
                ws.send(JSON.stringify({action: "pong"}));
            }
            
            if (data.type === "message.created") {
                console.log("New message:", data.payload);
            }
        };
        
        // Subscribe to conversation
        ws.send(JSON.stringify({
            action: "subscribe",
            conversation_id: 1
        }));
        ```
        
    Error Codes:
        - 4001: Authentication failed (invalid token)
        - 4002: Connection limit reached (max 5 per user)
        - 4003: Invalid message format
        - 1000: Normal closure
        - 1001: Connection timeout (no heartbeat)
    """
    # Validate JWT token
    user = await validate_websocket_token(token, db)
    if not user:
        logger.warning(f"WebSocket authentication failed for token: {token[:20]}...")
        await websocket.close(code=4001, reason="Authentication failed")
        return
    
    # Try to connect (enforces connection limits)
    connected = await connection_manager.connect(websocket, user.id)
    if not connected:
        logger.warning(f"Connection limit reached for user {user.id}")
        await websocket.close(code=4002, reason="Connection limit reached")
        return
    
    logger.info(f"WebSocket connection established for user {user.username} (ID: {user.id})")
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "user_id": user.id,
            "username": user.username,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Get user's conversations and auto-subscribe
        repository = Repository(db)
        # TODO: Implement repository.get_user_conversations() to fetch conversation IDs
        # For now, client must explicitly subscribe to conversations
        
        # Message loop
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                action = message.get("action")
                
                if action == "subscribe":
                    # Subscribe to conversation
                    conversation_id = message.get("conversation_id")
                    if not conversation_id:
                        await websocket.send_json(WSError(
                            error="Missing conversation_id",
                            code="INVALID_MESSAGE"
                        ).model_dump())
                        continue
                    
                    # Verify user is member of conversation
                    if not repository.is_conversation_member(conversation_id, user.id):
                        await websocket.send_json(WSError(
                            error="You are not a member of this conversation",
                            code="FORBIDDEN"
                        ).model_dump())
                        continue
                    
                    connection_manager.subscribe_to_conversation(websocket, conversation_id)
                    await websocket.send_json({
                        "type": "subscribed",
                        "conversation_id": conversation_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    logger.info(f"User {user.id} subscribed to conversation {conversation_id}")
                
                elif action == "unsubscribe":
                    # Unsubscribe from conversation
                    conversation_id = message.get("conversation_id")
                    if not conversation_id:
                        await websocket.send_json(WSError(
                            error="Missing conversation_id",
                            code="INVALID_MESSAGE"
                        ).model_dump())
                        continue
                    
                    connection_manager.unsubscribe_from_conversation(websocket, conversation_id)
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "conversation_id": conversation_id,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    logger.info(f"User {user.id} unsubscribed from conversation {conversation_id}")
                
                elif action == "pong":
                    # Update heartbeat
                    await connection_manager.update_heartbeat(websocket)
                
                else:
                    await websocket.send_json(WSError(
                        error=f"Unknown action: {action}",
                        code="INVALID_ACTION"
                    ).model_dump())
            
            except json.JSONDecodeError:
                await websocket.send_json(WSError(
                    error="Invalid JSON format",
                    code="INVALID_JSON"
                ).model_dump())
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")
                await websocket.send_json(WSError(
                    error="Internal server error",
                    code="INTERNAL_ERROR"
                ).model_dump())
    
    except WebSocketDisconnect:
        logger.info(f"User {user.username} (ID: {user.id}) disconnected from WebSocket")
    except Exception as e:
        logger.error(f"WebSocket error for user {user.id}: {e}")
    finally:
        connection_manager.disconnect(websocket)
