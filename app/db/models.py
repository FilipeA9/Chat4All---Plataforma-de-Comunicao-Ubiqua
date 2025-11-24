"""
SQLAlchemy ORM models.
Defines database schema using declarative base.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, JSON, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from db.database import Base


class ConversationType(str, enum.Enum):
    """Conversation type enum."""
    PRIVATE = "private"
    GROUP = "group"


class MessageStatus(str, enum.Enum):
    """Message processing status enum."""
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    FAILED = "failed"


class FileStatus(str, enum.Enum):
    """File upload status enum."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(UUID(as_uuid=True), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(Enum(ConversationType), nullable=False)
    name = Column(String(100))
    description = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ConversationMember(Base):
    __tablename__ = "conversation_members"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(Enum(MessageStatus), default=MessageStatus.ACCEPTED, nullable=False)
    channels = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FileMetadata(Base):
    __tablename__ = "file_metadata"
    
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=False)
    minio_object_name = Column(String(500), unique=True, nullable=False)
    checksum = Column(String(64))
    status = Column(Enum(FileStatus), default=FileStatus.PENDING, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
