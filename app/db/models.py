"""
SQLAlchemy ORM models for Chat4All database.
Defines all entities: User, Conversation, ConversationMember, Message,
MessageStatusHistory, FileMetadata, FileChunk, AuthSession.
"""
import enum
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, Text, 
    BigInteger, Boolean, Enum as SQLEnum, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from db.database import Base


# ENUM Types
class ConversationType(str, enum.Enum):
    """Type of conversation."""
    PRIVATE = "private"
    GROUP = "group"


class MessageStatus(str, enum.Enum):
    """Status of message delivery."""
    ACCEPTED = "accepted"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"


class FileStatus(str, enum.Enum):
    """Status of file upload."""
    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


# Models
class User(Base):
    """User entity - represents system users."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    conversation_memberships = relationship("ConversationMember", back_populates="user")
    messages = relationship("Message", back_populates="sender")
    auth_sessions = relationship("AuthSession", back_populates="user")


class Conversation(Base):
    """Conversation entity - represents private or group conversations."""
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(SQLEnum(ConversationType), nullable=False)
    name = Column(String(100), nullable=True)  # For group conversations
    description = Column(Text, nullable=True)  # For group conversations
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    members = relationship("ConversationMember", back_populates="conversation")
    messages = relationship("Message", back_populates="conversation")


class ConversationMember(Base):
    """Junction table for many-to-many relationship between users and conversations."""
    __tablename__ = "conversation_members"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="members")
    user = relationship("User", back_populates="conversation_memberships")


class Message(Base):
    """Message entity - represents messages sent in conversations."""
    __tablename__ = "messages"
    
    # UUID as primary key for idempotency
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    payload = Column(JSON, nullable=False)  # {"type": "text", "content": "..."} or {"type": "file", "file_id": "..."}
    status = Column(SQLEnum(MessageStatus), default=MessageStatus.ACCEPTED, nullable=False)
    channels = Column(JSON, nullable=False)  # ["whatsapp", "instagram"] or ["all"]
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", back_populates="messages")
    status_history = relationship("MessageStatusHistory", back_populates="message")


class MessageStatusHistory(Base):
    """Audit trail for message status changes."""
    __tablename__ = "message_status_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False, index=True)
    status = Column(SQLEnum(MessageStatus), nullable=False)
    channel = Column(String(50), nullable=True)  # Which channel this status update is for
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    details = Column(JSON, nullable=True)  # Additional context
    
    # Relationships
    message = relationship("Message", back_populates="status_history")


class FileMetadata(Base):
    """Metadata for uploaded files stored in MinIO."""
    __tablename__ = "file_metadata"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=False)
    checksum = Column(String(64), nullable=True)  # SHA-256 checksum
    status = Column(SQLEnum(FileStatus), default=FileStatus.UPLOADING, nullable=False)
    minio_object_name = Column(String(255), nullable=False)  # Object path in MinIO
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    chunks = relationship("FileChunk", back_populates="file")


class FileChunk(Base):
    """Tracks chunks for resumable file uploads."""
    __tablename__ = "file_chunks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(UUID(as_uuid=True), ForeignKey("file_metadata.id"), nullable=False, index=True)
    chunk_number = Column(Integer, nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    file = relationship("FileMetadata", back_populates="chunks")


class AuthSession(Base):
    """Simple token-based authentication sessions."""
    __tablename__ = "auth_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(UUID(as_uuid=True), unique=True, nullable=False, index=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="auth_sessions")


# ============================================================================
# E1: OAuth 2.0 Authentication Models (Epic 0)
# ============================================================================

class AccessToken(Base):
    """OAuth 2.0 access tokens (JWT, 15min expiration)."""
    __tablename__ = "access_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False)  # SHA-256 hash of JWT
    scope = Column(String(255), default="read write", nullable=False)
    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RefreshToken(Base):
    """OAuth 2.0 refresh tokens (opaque, 30 day expiration)."""
    __tablename__ = "refresh_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False)  # SHA-256 hash
    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ============================================================================
# E2: Transactional Outbox Pattern (Epic 2 - Resilient Data Plane)
# ============================================================================

class OutboxEvent(Base):
    """Transactional Outbox for at-least-once Kafka event delivery."""
    __tablename__ = "outbox_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type = Column(String(50), nullable=False)  # 'message', 'conversation', 'file'
    aggregate_id = Column(UUID(as_uuid=True), nullable=False)
    event_type = Column(String(100), nullable=False)  # 'message.created', 'file.uploaded'
    payload = Column(JSON, nullable=False)  # Complete event data
    published = Column(Boolean, default=False, nullable=False)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    version = Column(Integer, default=1, nullable=False)  # Retry counter
    error_message = Column(Text, nullable=True)


# ============================================================================
# E3: WebSocket Connections (Epic 1 - Real-Time Communication)
# ============================================================================

class WebSocketConnection(Base):
    """Active WebSocket connections for real-time notifications."""
    __tablename__ = "websocket_connections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id = Column(String(255), unique=True, nullable=False)
    api_instance_id = Column(String(255), nullable=False)  # API pod identifier
    subscribed_conversations = Column(JSON, default=list, nullable=False)  # Array of conversation IDs
    connected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_ping_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    disconnected_at = Column(DateTime, nullable=True)


# ============================================================================
# E4: Enhanced File Upload Models (Epic 4 - Full-Featured File Upload)
# ============================================================================

class File(Base):
    """
    Enhanced file upload metadata with resumable chunked uploads.
    Supports files up to 2GB with 5-10MB chunks stored in MinIO.
    """
    __tablename__ = "files"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    uploader_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)  # In bytes, max 2GB
    mime_type = Column(String(100), nullable=False)
    checksum_sha256 = Column(String(64), nullable=True)  # SHA-256 of complete merged file
    storage_key = Column(String(500), nullable=True)  # MinIO key after merge (e.g., "files/{upload_id}")
    status = Column(SQLEnum(FileStatus), default=FileStatus.PENDING, nullable=False)
    chunk_size = Column(Integer, nullable=False)  # Chunk size in bytes (5-10MB recommended)
    total_chunks = Column(Integer, nullable=False)  # ceil(file_size / chunk_size)
    uploaded_chunks = Column(Integer, default=0, nullable=False)  # Count of uploaded chunks
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    conversation = relationship("Conversation")
    uploader = relationship("User")
    chunks = relationship("FileChunkModel", back_populates="file", cascade="all, delete-orphan")


class FileChunkModel(Base):
    """
    Individual file chunk for resumable uploads.
    Each chunk is stored temporarily in MinIO (e.g., chunks/{file_id}/{chunk_number}).
    After all chunks are uploaded, they are merged into the final file and deleted.
    """
    __tablename__ = "file_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_number = Column(Integer, nullable=False)  # 1-based index (1, 2, 3, ..., total_chunks)
    chunk_size = Column(Integer, nullable=False)  # Actual size in bytes (may be smaller for last chunk)
    storage_key = Column(String(500), nullable=False)  # MinIO key (e.g., "chunks/{file_id}/chunk-001")
    checksum_sha256 = Column(String(64), nullable=True)  # Optional chunk-level checksum
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    file = relationship("File", back_populates="chunks")
