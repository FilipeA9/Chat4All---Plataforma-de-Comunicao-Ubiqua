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
    Request schema for authentication.
    
    Attributes:
        username: User's unique username (1-50 characters)
        password: User's password (plain text, will be hashed server-side)
        
    Example:
        ```json
        {
            "username": "user1",
            "password": "password123"
        }
        ```
    """
    username: str = Field(..., min_length=1, max_length=50, description="User's unique username")
    password: str = Field(..., min_length=1, description="User's password")


class TokenResponse(BaseModel):
    """
    Response schema for authentication.
    
    Attributes:
        token: UUID v4 token for API authentication (include in Authorization header)
        expires_at: Token expiration timestamp (UTC)
        user_id: Authenticated user's unique identifier
        username: Authenticated user's username
        
    Example:
        ```json
        {
            "token": "550e8400-e29b-41d4-a716-446655440000",
            "expires_at": "2025-11-25T14:30:00Z",
            "user_id": 1,
            "username": "user1"
        }
        ```
    """
    token: str = Field(..., description="UUID v4 token for API authentication")
    expires_at: datetime = Field(..., description="Token expiration timestamp (UTC)")
    user_id: int = Field(..., description="Authenticated user's unique identifier")
    username: str = Field(..., description="Authenticated user's username")


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


# File Upload Schemas
class FileInitiateRequest(BaseModel):
    """
    Request schema for initiating file upload.
    
    Attributes:
        filename: Original filename (1-255 characters)
        size_bytes: File size in bytes (maximum 2GB = 2,147,483,648 bytes)
        mime_type: File MIME type (e.g., "image/png", "application/pdf")
        
    Example:
        ```json
        {
            "filename": "presentation.pdf",
            "size_bytes": 5242880,
            "mime_type": "application/pdf"
        }
        ```
    """
    filename: str = Field(..., min_length=1, max_length=255, description="Original filename")
    size_bytes: int = Field(..., gt=0, le=2_147_483_648, description="File size in bytes (max 2GB)")
    mime_type: str = Field(..., max_length=100, description="File MIME type")


class FileInitiateResponse(BaseModel):
    """
    Response schema for file upload initiation.
    
    Attributes:
        file_id: Generated file UUID (use this in POST /v1/files/complete)
        upload_url: Presigned URL for direct upload to MinIO (PUT request)
        expires_at: Presigned URL expiration time (valid for 1 hour)
    """
    file_id: UUID = Field(..., description="Generated file UUID")
    upload_url: str = Field(..., description="Presigned URL for direct upload (PUT request)")
    expires_at: datetime = Field(..., description="URL expiration timestamp (UTC)")


class FileCompleteRequest(BaseModel):
    """
    Request schema for completing file upload.
    
    Attributes:
        file_id: UUID of the file (from POST /v1/files/initiate)
        checksum: SHA-256 checksum of uploaded file (64 hex characters for verification)
        
    Example:
        ```json
        {
            "file_id": "550e8400-e29b-41d4-a716-446655440000",
            "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        }
        ```
    """
    file_id: UUID = Field(..., description="File UUID from initiate response")
    checksum: str = Field(..., min_length=64, max_length=64, description="SHA-256 checksum (64 hex characters)")


class FileCompleteResponse(BaseModel):
    """
    Response schema for file upload completion.
    
    Attributes:
        file_id: Completed file UUID (use in message payload)
        filename: Original filename
        size_bytes: File size in bytes
        status: File status (should be "completed")
        download_url: Presigned URL for downloading file (valid for 24 hours)
    """
    file_id: UUID = Field(..., description="Completed file UUID")
    filename: str = Field(..., description="Original filename")
    size_bytes: int = Field(..., description="File size in bytes")
    status: str = Field(..., description="File status (completed)")
    download_url: str = Field(..., description="Presigned download URL (valid 24h)")


# Error Schemas
class ErrorResponse(BaseModel):
    """Standard error response schema."""
    detail: str
    error_code: Optional[str] = None
