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
