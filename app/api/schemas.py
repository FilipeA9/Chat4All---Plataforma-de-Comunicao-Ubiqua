"""
Pydantic schemas for request/response validation.
Defines all data transfer objects (DTOs) for the API.
"""
from datetime import datetime
from typing import List, Optional, Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


# Authentication Schemas
class TokenRequest(BaseModel):
    """
    OAuth 2.0 Client Credentials token request.
    
    Attributes:
        grant_type: Must be "client_credentials"
        client_id: User's username (OAuth 2.0 client identifier)
        client_secret: User's password (OAuth 2.0 client secret)
        scope: Optional OAuth 2.0 scopes (default: "read write")
        
    Example:
        ```json
        {
            "grant_type": "client_credentials",
            "client_id": "user1",
            "client_secret": "password123",
            "scope": "read write"
        }
        ```
    """
    grant_type: Literal["client_credentials"] = Field(..., description="OAuth 2.0 grant type")
    client_id: str = Field(..., min_length=1, max_length=50, description="Client identifier (username)")
    client_secret: str = Field(..., min_length=1, description="Client secret (password)")
    scope: Optional[str] = Field("read write", description="OAuth 2.0 scopes")


class TokenResponse(BaseModel):
    """
    OAuth 2.0 token response (RFC 6749).
    
    Attributes:
        access_token: JWT access token (15min expiration)
        refresh_token: Opaque refresh token (30 day expiration)
        token_type: Always "Bearer"
        expires_in: Access token lifetime in seconds (900 for 15min)
        scope: Granted OAuth 2.0 scopes
        
    Example:
        ```json
        {
            "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "a1b2c3d4e5f6...",
            "token_type": "Bearer",
            "expires_in": 900,
            "scope": "read write"
        }
        ```
    """
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Opaque refresh token")
    token_type: str = Field("Bearer", description="Token type")
    expires_in: int = Field(..., description="Access token lifetime in seconds")
    scope: str = Field(..., description="Granted OAuth 2.0 scopes")


class RefreshTokenRequest(BaseModel):
    """
    OAuth 2.0 refresh token request.
    
    Attributes:
        grant_type: Must be "refresh_token"
        refresh_token: Previously issued refresh token
        
    Example:
        ```json
        {
            "grant_type": "refresh_token",
            "refresh_token": "a1b2c3d4e5f6..."
        }
        ```
    """
    grant_type: Literal["refresh_token"] = Field(..., description="OAuth 2.0 grant type")
    refresh_token: str = Field(..., description="Refresh token")


class RevokeTokenRequest(BaseModel):
    """
    OAuth 2.0 token revocation request (RFC 7009).
    
    Attributes:
        token: Token to revoke (refresh token)
        token_type_hint: Optional hint about token type ("refresh_token")
        
    Example:
        ```json
        {
            "token": "a1b2c3d4e5f6...",
            "token_type_hint": "refresh_token"
        }
        ```
    """
    token: str = Field(..., description="Token to revoke")
    token_type_hint: Optional[str] = Field("refresh_token", description="Token type hint")


# Conversation Schemas
class ConversationCreate(BaseModel):
    """
    Request schema for creating a conversation.
    
    Attributes:
        type: Conversation type - "private" (exactly 2 members) or "group" (3-100 members)
        member_ids: List of user IDs to add as conversation members (minimum 2)
        name: Optional conversation name (max 100 characters, required for groups)
        description: Optional conversation description
        
    Examples:
        Private conversation:
        ```json
        {
            "type": "private",
            "member_ids": [1, 2]
        }
        ```
        
        Group conversation:
        ```json
        {
            "type": "group",
            "member_ids": [1, 2, 3, 4],
            "name": "Project Team",
            "description": "Discussion for project alpha"
        }
        ```
    """
    type: Literal["private", "group"] = Field(..., description="Conversation type: private (2 members) or group (3-100 members)")
    member_ids: List[int] = Field(..., min_items=2, description="List of user IDs to add as members")
    name: Optional[str] = Field(None, max_length=100, description="Conversation name (recommended for groups)")
    description: Optional[str] = Field(None, description="Optional conversation description")


class ConversationResponse(BaseModel):
    """
    Response schema for conversation.
    
    Attributes:
        id: Unique conversation identifier
        type: Conversation type ("private" or "group")
        name: Conversation name (may be null for private conversations)
        description: Conversation description (optional)
        created_at: Timestamp when conversation was created (UTC)
        member_count: Total number of conversation members
    """
    id: int = Field(..., description="Unique conversation identifier")
    type: str = Field(..., description="Conversation type (private or group)")
    name: Optional[str] = Field(None, description="Conversation name")
    description: Optional[str] = Field(None, description="Conversation description")
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")
    member_count: int = Field(..., description="Total number of members")
    
    model_config = ConfigDict(from_attributes=True)


class ConversationListItem(BaseModel):
    """
    Single conversation item in list response.
    
    Attributes:
        conversation_id: Unique conversation identifier
        conversation_type: Conversation type ("private" or "group")
        conversation_name: Conversation name (may be null)
        description: Conversation description (optional)
        last_message_timestamp: Timestamp of most recent message (null if no messages)
        last_message_content: Preview of last message text (truncated to 100 chars)
        last_message_sender: Username of last message sender
        unread_count: Number of unread messages for this user
        conversation_created_at: Timestamp when conversation was created
    """
    conversation_id: int = Field(..., description="Conversation identifier")
    conversation_type: str = Field(..., description="Conversation type")
    conversation_name: str | None = Field(None, description="Conversation name")
    description: str | None = Field(None, description="Conversation description")
    last_message_timestamp: datetime | None = Field(None, description="Last message timestamp")
    last_message_content: str | None = Field(None, description="Last message preview")
    last_message_sender: str | None = Field(None, description="Last message sender username")
    unread_count: int = Field(0, description="Unread message count")
    conversation_created_at: datetime = Field(..., description="Conversation creation timestamp")


class ConversationListResponse(BaseModel):
    """
    Response schema for conversation list with pagination.
    
    Attributes:
        items: List of conversations
        total: Total number of conversations for this user
        limit: Maximum items per page
        offset: Number of items skipped
        has_more: Whether more items are available
    """
    items: List[ConversationListItem] = Field(..., description="Conversation items")
    total: int = Field(..., description="Total conversation count")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Items skipped")
    has_more: bool = Field(..., description="Whether more pages available")


# Message Schemas
class MessagePayloadText(BaseModel):
    """
    Payload schema for text messages.
    
    Attributes:
        type: Must be "text" for text messages
        content: Message text content (minimum 1 character)
        
    Example:
        ```json
        {
            "type": "text",
            "content": "Hello, team!"
        }
        ```
    """
    type: Literal["text"] = Field(..., description="Message type identifier")
    content: str = Field(..., min_length=1, description="Message text content")


class MessagePayloadFile(BaseModel):
    """
    Payload schema for file messages.
    
    Attributes:
        type: Must be "file" for file messages
        file_id: UUID of the uploaded file (from POST /v1/files/complete)
        
    Example:
        ```json
        {
            "type": "file",
            "file_id": "550e8400-e29b-41d4-a716-446655440000"
        }
        ```
    """
    type: Literal["file"] = Field(..., description="Message type identifier")
    file_id: UUID = Field(..., description="UUID of uploaded file")


class MessageCreate(BaseModel):
    """
    Request schema for creating a message.
    
    Attributes:
        message_id: Client-generated UUID for idempotency (prevent duplicate sends)
        conversation_id: ID of the conversation to send message to
        payload: Message payload (text or file)
        channels: List of delivery channels ("whatsapp", "instagram", or "all")
        
    Examples:
        Text message:
        ```json
        {
            "message_id": "550e8400-e29b-41d4-a716-446655440000",
            "conversation_id": 1,
            "payload": {"type": "text", "content": "Hello!"},
            "channels": ["whatsapp", "instagram"]
        }
        ```
        
        File message:
        ```json
        {
            "message_id": "650e8400-e29b-41d4-a716-446655440000",
            "conversation_id": 1,
            "payload": {"type": "file", "file_id": "750e8400-e29b-41d4-a716-446655440000"},
            "channels": ["all"]
        }
        ```
    """
    message_id: UUID = Field(..., description="Client-generated UUID for idempotency")
    conversation_id: int = Field(..., description="Target conversation ID")
    payload: MessagePayloadText | MessagePayloadFile = Field(..., description="Message payload (text or file)")
    channels: List[str] = Field(..., min_items=1, description="Delivery channels: whatsapp, instagram, or all")


class MessageResponse(BaseModel):
    """
    Response schema for message.
    
    Attributes:
        message_id: Unique message identifier (UUID)
        conversation_id: ID of the conversation containing this message
        sender_id: ID of the user who sent the message
        sender_username: Username of the sender
        payload: Message payload (includes type, content/file_id, and enriched file metadata)
        status: Message status (accepted, delivered, failed)
        channels: Delivery channels for this message
        created_at: Timestamp when message was created (UTC)
    """
    message_id: UUID = Field(..., description="Unique message identifier")
    conversation_id: int = Field(..., description="Parent conversation ID")
    sender_id: int = Field(..., description="Sender's user ID")
    sender_username: str = Field(..., description="Sender's username")
    payload: dict = Field(..., description="Message payload with type and content/file data")
    status: str = Field(..., description="Message status: accepted, delivered, or failed")
    channels: List[str] = Field(..., description="Delivery channels")
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")
    
    model_config = ConfigDict(from_attributes=True)


class MessageListResponse(BaseModel):
    """Response schema for list of messages."""
    messages: List[MessageResponse]
    total: int
    limit: int
    offset: int


# File Upload Schemas (Chunked)
class FileInitiateRequest(BaseModel):
    """
    Request schema for initiating chunked file upload.
    
    Attributes:
        conversation_id: UUID of conversation where file will be shared
        filename: Original filename (1-255 characters)
        file_size: File size in bytes (maximum 2GB = 2,147,483,648 bytes)
        mime_type: File MIME type (e.g., "image/png", "application/pdf")
        checksum_sha256: Optional SHA-256 checksum of complete file for integrity verification
        chunk_size: Optional chunk size in bytes (1MB-50MB, recommended 5-10MB)
        
    Example:
        ```json
        {
            "conversation_id": 123,
            "filename": "vacation_video.mp4",
            "file_size": 1073741824,
            "mime_type": "video/mp4",
            "checksum_sha256": "abc123def456...",
            "chunk_size": 5242880
        }
        ```
    """
    conversation_id: int = Field(..., description="Conversation ID where file will be shared")
    filename: str = Field(..., min_length=1, max_length=255, description="Original filename")
    file_size: int = Field(..., gt=0, le=2_147_483_648, description="File size in bytes (max 2GB)")
    mime_type: str = Field(..., max_length=100, description="File MIME type")
    checksum_sha256: str | None = Field(None, min_length=64, max_length=64, description="SHA-256 checksum (optional)")
    chunk_size: int | None = Field(
        10_485_760,  # 10MB default
        ge=1_048_576,  # 1MB minimum
        le=52_428_800,  # 50MB maximum
        description="Chunk size in bytes (1MB-50MB)"
    )


class FileInitiateResponse(BaseModel):
    """
    Response schema for chunked file upload initiation.
    
    Attributes:
        upload_id: Upload session UUID (use in subsequent chunk uploads)
        total_chunks: Total number of chunks to upload
        chunk_size: Chunk size in bytes (all chunks except last)
        expires_at: Upload session expiration (24 hours from creation)
    """
    upload_id: UUID = Field(..., description="Upload session UUID")
    total_chunks: int = Field(..., description="Total number of chunks to upload")
    chunk_size: int = Field(..., description="Chunk size in bytes")
    expires_at: datetime = Field(..., description="Upload session expiration timestamp")


class FileChunkUploadResponse(BaseModel):
    """
    Response schema for chunk upload.
    
    Attributes:
        upload_id: Upload session UUID
        chunk_number: Chunk number just uploaded
        uploaded_chunks: Total count of uploaded chunks
        total_chunks: Total number of chunks
        percentage: Upload progress percentage (0-100)
    """
    upload_id: UUID = Field(..., description="Upload session UUID")
    chunk_number: int = Field(..., description="Chunk number just uploaded")
    uploaded_chunks: int = Field(..., description="Count of uploaded chunks")
    total_chunks: int = Field(..., description="Total number of chunks")
    percentage: float = Field(..., description="Upload progress percentage")


class FileStatusResponse(BaseModel):
    """
    Response schema for upload status query.
    
    Attributes:
        upload_id: Upload session UUID
        status: Upload status (pending/uploading/merging/completed/failed)
        uploaded_chunks: Count of uploaded chunks
        total_chunks: Total number of chunks
        percentage: Upload progress percentage
        missing_chunks: List of chunk numbers not yet uploaded (optional)
        file_id: Final file UUID (only when status=completed)
        download_url: Download URL (only when status=completed)
        created_at: Upload session creation timestamp
        expires_at: Upload session expiration timestamp
        completed_at: Upload completion timestamp (only when status=completed)
    """
    upload_id: UUID = Field(..., description="Upload session UUID")
    status: str = Field(..., description="Upload status")
    uploaded_chunks: int = Field(..., description="Count of uploaded chunks")
    total_chunks: int = Field(..., description="Total number of chunks")
    percentage: float = Field(..., description="Upload progress percentage")
    missing_chunks: List[int] | None = Field(None, description="Missing chunk numbers")
    file_id: UUID | None = Field(None, description="Final file UUID (when completed)")
    download_url: str | None = Field(None, description="Download URL (when completed)")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: datetime | None = Field(None, description="Expiration timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")


class FileCompleteResponse(BaseModel):
    """
    Response schema for file upload completion.
    
    Attributes:
        upload_id: Upload session UUID
        status: Upload status (merging/completed/failed)
        message: Human-readable status message
        estimated_completion: Estimated merge completion time
    """
    upload_id: UUID = Field(..., description="Upload session UUID")
    status: str = Field(..., description="Upload status after completion")
    message: str = Field(..., description="Status message")
    estimated_completion: datetime | None = Field(None, description="Estimated completion time")


# WebSocket Message Schemas
class WSMessageCreated(BaseModel):
    """WebSocket event: New message created."""
    type: str = Field(default="message.created", description="Event type")
    message_id: str = Field(..., description="Message UUID")
    conversation_id: int = Field(..., description="Conversation ID")
    sender_id: int = Field(..., description="Sender user ID")
    sender_username: str = Field(..., description="Sender username")
    payload: dict = Field(..., description="Message payload (text or file)")
    channels: List[str] = Field(..., description="Target channels")
    created_at: datetime = Field(..., description="Message creation timestamp")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")


class WSMessageDelivered(BaseModel):
    """WebSocket event: Message delivered to channel."""
    type: str = Field(default="message.delivered", description="Event type")
    message_id: str = Field(..., description="Message UUID")
    conversation_id: int = Field(..., description="Conversation ID")
    channel: str = Field(..., description="Channel that received the message")
    delivered_at: datetime = Field(..., description="Delivery timestamp")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")


class WSMessageRead(BaseModel):
    """WebSocket event: Message marked as read."""
    type: str = Field(default="message.read", description="Event type")
    message_id: str = Field(..., description="Message UUID")
    conversation_id: int = Field(..., description="Conversation ID")
    user_id: int = Field(..., description="User who read the message")
    username: str = Field(..., description="Username who read the message")
    read_at: datetime = Field(..., description="Read timestamp")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")


class WSConversationRead(BaseModel):
    """WebSocket event: All messages in conversation marked as read."""
    type: str = Field(default="conversation.read", description="Event type")
    conversation_id: int = Field(..., description="Conversation ID")
    user_id: int = Field(..., description="User who read the conversation")
    username: str = Field(..., description="Username who read the conversation")
    message_count: int = Field(..., description="Number of messages marked as read")
    read_at: datetime = Field(..., description="Read timestamp")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")


class WSHeartbeat(BaseModel):
    """WebSocket event: Heartbeat ping/pong."""
    type: str = Field(..., description="Event type (ping or pong)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")


class WSError(BaseModel):
    """WebSocket event: Error notification."""
    type: str = Field(default="error", description="Event type")
    error: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Error code")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")


class WSSubscribe(BaseModel):
    """WebSocket command: Subscribe to conversation."""
    action: str = Field(default="subscribe", description="Action type")
    conversation_id: int = Field(..., description="Conversation ID to subscribe to")


class WSUnsubscribe(BaseModel):
    """WebSocket command: Unsubscribe from conversation."""
    action: str = Field(default="unsubscribe", description="Action type")
    conversation_id: int = Field(..., description="Conversation ID to unsubscribe from")


# Error Schemas
class ErrorResponse(BaseModel):
    """Standard error response schema."""
    detail: str
    error_code: Optional[str] = None
