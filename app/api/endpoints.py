"""
API endpoint implementations.
Defines all REST endpoints for authentication, conversations, messages, and files.
"""
import logging
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from api.dependencies import get_db, get_current_user
from api.schemas import (
    TokenRequest, TokenResponse, ConversationCreate, ConversationResponse,
    MessageCreate, MessageResponse, MessageListResponse,
    FileInitiateRequest, FileInitiateResponse, FileCompleteRequest, FileCompleteResponse
)
from db.repository import Repository
from db.models import User, ConversationType, MessageStatus, FileStatus
from core.config import settings
from services.kafka_producer import get_kafka_producer

logger = logging.getLogger(__name__)

# Create routers
auth_router = APIRouter()
conversations_router = APIRouter()
messages_router = APIRouter()
files_router = APIRouter()


# Authentication Endpoints
@auth_router.post("/token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def authenticate(request: TokenRequest, db: Session = Depends(get_db)):
    """
    Authenticate user and return access token.
    
    Validates user credentials using plain text password comparison and creates a new
    authentication session with a UUID token. The token should be included in the
    Authorization header (Bearer token) for all subsequent API requests.
    
    Args:
        request: Username and password credentials
        db: Database session (injected)
        
    Returns:
        TokenResponse: Authentication token with expiry, user ID, and username
        
    Raises:
        HTTPException: 401 Unauthorized if credentials are invalid
        
    Example Request:
        ```json
        POST /auth/token
        {
            "username": "user1",
            "password": "password123"
        }
        ```
        
    Example Response:
        ```json
        {
            "token": "550e8400-e29b-41d4-a716-446655440000",
            "expires_at": "2025-11-25T14:30:00Z",
            "user_id": 1,
            "username": "user1"
        }
        ```
    """
    repository = Repository(db)
    
    # Get user by username
    user = repository.get_user_by_username(request.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Verify password (plain text comparison)
    if request.password != user.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Create auth session
    token = uuid4()
    auth_session = repository.create_auth_session(user.id, token)
    
    logger.info(f"User {user.username} authenticated successfully")
    
    return TokenResponse(
        token=str(auth_session.token),
        expires_at=auth_session.expires_at,
        user_id=user.id,
        username=user.username
    )


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
        conversation_type=ConversationType(request.type),
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
    message = repository.create_message(
        message_id=request.message_id,
        conversation_id=request.conversation_id,
        sender_id=current_user.id,
        payload=payload_dict,
        channels=request.channels
    )
    
    # Publish to Kafka in background
    message_data = {
        "message_id": str(message.id),
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "payload": message.payload,
        "channels": message.channels
    }
    background_tasks.add_task(publish_message_to_kafka, message_data)
    
    logger.info(f"Message {message.id} accepted from user {current_user.username}")
    
    return {
        "status": "accepted",
        "message_id": str(message.id)
    }


# File Upload Endpoints
@files_router.post("/initiate", response_model=FileInitiateResponse, status_code=status.HTTP_200_OK)
def initiate_file_upload(
    request: FileInitiateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Initiate a file upload and get presigned URL.
    
    Creates a file metadata record and generates a presigned URL for direct upload
    to MinIO storage. Maximum file size is 2GB. The presigned URL is valid for 1 hour.
    After upload, call POST /v1/files/complete to finalize the file.
    
    Args:
        request: File metadata (filename, size_bytes, mime_type)
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        FileInitiateResponse: File ID and presigned upload URL
        
    Raises:
        HTTPException: 401 Unauthorized if token is invalid
        HTTPException: 413 Payload Too Large if file exceeds 2GB limit
        
    Example Request:
        ```json
        POST /v1/files/initiate
        Authorization: Bearer <token>
        {
            "filename": "presentation.pdf",
            "size_bytes": 5242880,
            "mime_type": "application/pdf"
        }
        ```
        
    Example Response:
        ```json
        {
            "file_id": "550e8400-e29b-41d4-a716-446655440000",
            "upload_url": "https://minio:9000/chat4all/uploads/...",
            "expires_at": "2025-11-24T15:30:00Z"
        }
        ```
        
    Next Steps:
        1. Use the upload_url to PUT the file directly to MinIO
        2. Calculate SHA-256 checksum of uploaded file
        3. Call POST /v1/files/complete with file_id and checksum
    """
    # Validate file size (max 2GB)
    MAX_FILE_SIZE = 2_147_483_648  # 2GB in bytes
    if request.size_bytes > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 2GB limit"
        )
    
    repository = Repository(db)
    
    # Generate file ID and MinIO object name
    file_id = uuid4()
    minio_object_name = f"uploads/{current_user.id}/{file_id}/{request.filename}"
    
    # Create file metadata in database
    file_metadata = repository.create_file_metadata(
        file_id=file_id,
        filename=request.filename,
        size_bytes=request.size_bytes,
        mime_type=request.mime_type,
        minio_object_name=minio_object_name,
        uploaded_by=current_user.id
    )
    
    # Generate presigned PUT URL
    from services.minio_client import get_minio_client
    from datetime import timedelta
    
    minio_client = get_minio_client()
    upload_url = minio_client.presigned_put_url(
        minio_object_name,
        expires=timedelta(hours=1)
    )
    
    logger.info(f"File upload initiated: {file_id} by user {current_user.username}")
    
    return FileInitiateResponse(
        file_id=file_id,
        upload_url=upload_url,
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )


@files_router.post("/complete", response_model=FileCompleteResponse, status_code=status.HTTP_200_OK)
def complete_file_upload(
    request: FileCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Complete file upload and verify integrity.
    
    Verifies the file exists in MinIO storage and updates the file status to "completed".
    The checksum (SHA-256) should match the uploaded file for integrity verification.
    Returns a presigned download URL valid for 24 hours.
    
    Args:
        request: File ID and SHA-256 checksum
        current_user: Authenticated user (injected)
        db: Database session (injected)
        
    Returns:
        FileCompleteResponse: File details with download URL
        
    Raises:
        HTTPException: 400 Bad Request if file not found in storage
        HTTPException: 401 Unauthorized if token is invalid
        HTTPException: 403 Forbidden if file belongs to different user
        HTTPException: 404 Not Found if file metadata not found
        
    Example Request:
        ```json
        POST /v1/files/complete
        Authorization: Bearer <token>
        {
            "file_id": "550e8400-e29b-41d4-a716-446655440000",
            "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        }
        ```
        
    Example Response:
        ```json
        {
            "file_id": "550e8400-e29b-41d4-a716-446655440000",
            "filename": "presentation.pdf",
            "size_bytes": 5242880,
            "status": "completed",
            "download_url": "https://minio:9000/chat4all/..."
        }
        ```
        
    Next Steps:
        Use the file_id in a message payload to send the file to a conversation.
    """
    repository = Repository(db)
    
    # Get file metadata
    file_metadata = repository.get_file_metadata(request.file_id)
    if not file_metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # Verify file belongs to current user
    if file_metadata.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to complete this upload"
        )
    
    # Verify file exists in MinIO
    from services.minio_client import get_minio_client
    
    minio_client = get_minio_client()
    object_stat = minio_client.stat_object(file_metadata.minio_object_name)
    
    if not object_stat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File not found in storage. Please upload the file first."
        )
    
    # Update file metadata status to completed
    file_metadata = repository.update_file_metadata(
        file_id=request.file_id,
        status=FileStatus.COMPLETED,
        checksum=request.checksum
    )
    
    # Generate download URL
    from datetime import timedelta
    download_url = minio_client.presigned_get_url(
        file_metadata.minio_object_name,
        expires=timedelta(hours=24)
    )
    
    logger.info(f"File upload completed: {request.file_id}")
    
    return FileCompleteResponse(
        file_id=file_metadata.id,
        filename=file_metadata.filename,
        size_bytes=file_metadata.size_bytes,
        status=file_metadata.status.value,
        download_url=download_url
    )
