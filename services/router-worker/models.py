import uuid
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, JSON, Enum
from sqlalchemy.sql import func
from database import Base
import enum

class MessageStatus(str, enum.Enum):
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Em um sistema real teria ManyToMany com users, simplifiquei para o MVP

class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    
    sender = Column(String, nullable=False) # user_id
    channel = Column(String, default="chat4all") # chat4all, whatsapp, instagram
    
    content_type = Column(String, default="text") # text ou file
    payload = Column(JSON, nullable=False) # {"text": "ola"} ou {"file_id": "..."}
    
    status = Column(String, default=MessageStatus.SENT.value)
    metadata_info = Column(JSON, nullable=True) # priority, etc
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class FileMetadata(Base):
    __tablename__ = "files"
    
    id = Column(String, primary_key=True)
    uploader = Column(String, nullable=False)
    checksum = Column(String, nullable=True)
    size = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())