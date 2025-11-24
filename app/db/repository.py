"""
Repository layer for database operations.
Provides high-level methods for common database queries and operations.
"""
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from db.models import (
    User, Conversation, ConversationMember, Message, MessageStatusHistory,
    FileMetadata, FileChunk, AuthSession, ConversationType, MessageStatus, FileStatus
)
from core.config import settings


class Repository:
    """Repository class for database operations."""
    
    def __init__(self, db: Session):
        """
        Initialize repository with database session.
        
        Args:
            db: SQLAlchemy database session
        """
        self.db = db
    
    # User operations
    def create_user(self, username: str, password_hash: str, full_name: str) -> User:
        """Create a new user."""
        user = User(
            username=username,
            password_hash=password_hash,
            full_name=full_name
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.db.query(User).filter(User.username == username).first()
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()
    
    # Conversation operations
    def create_conversation(
        self, 
        conversation_type: ConversationType, 
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Conversation:
        """Create a new conversation."""
        conversation = Conversation(
            type=conversation_type,
            name=name,
            description=description
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation
    
    def get_conversation_by_id(self, conversation_id: int) -> Optional[Conversation]:
        """Get conversation by ID."""
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
    
    def add_conversation_member(self, conversation_id: int, user_id: int) -> ConversationMember:
        """Add a user as a member of a conversation."""
        member = ConversationMember(
            conversation_id=conversation_id,
            user_id=user_id
        )
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member
    
    def is_conversation_member(self, conversation_id: int, user_id: int) -> bool:
        """Check if user is a member of conversation."""
        member = self.db.query(ConversationMember).filter(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id
        ).first()
        return member is not None
    
    def get_conversation_members(self, conversation_id: int) -> List[User]:
        """Get all members of a conversation."""
        members = self.db.query(User).join(ConversationMember).filter(
            ConversationMember.conversation_id == conversation_id
        ).all()
        return members
    
    # Message operations
    def create_message(
        self,
        message_id: UUID,
        conversation_id: int,
        sender_id: int,
        payload: dict,
        channels: List[str]
    ) -> Message:
        """Create a new message."""
        message = Message(
            id=message_id,
            conversation_id=conversation_id,
            sender_id=sender_id,
            payload=payload,
            channels=channels,
            status=MessageStatus.ACCEPTED
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
    
    def get_message_by_id(self, message_id: UUID) -> Optional[Message]:
        """Get message by ID."""
        return self.db.query(Message).filter(Message.id == message_id).first()
    
    def get_conversation_messages(
        self, 
        conversation_id: int, 
        limit: int = 50, 
        offset: int = 0
    ) -> List[Message]:
        """Get messages from a conversation with pagination."""
        messages = self.db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.desc()).limit(limit).offset(offset).all()
        return messages
    
    def update_message_status(
        self, 
        message_id: UUID, 
        status: MessageStatus,
        channel: Optional[str] = None,
        details: Optional[dict] = None
    ) -> Message:
        """Update message status and create status history entry."""
        message = self.get_message_by_id(message_id)
        if message:
            message.status = status
            message.updated_at = datetime.utcnow()
            
            # Create status history entry
            history = MessageStatusHistory(
                message_id=message_id,
                status=status,
                channel=channel,
                details=details
            )
            self.db.add(history)
            self.db.commit()
            self.db.refresh(message)
        return message
    
    # File operations
    def create_file_metadata(
        self,
        file_id: UUID,
        filename: str,
        size_bytes: int,
        mime_type: str,
        minio_object_name: str,
        uploaded_by: int
    ) -> FileMetadata:
        """Create file metadata record."""
        file_metadata = FileMetadata(
            id=file_id,
            filename=filename,
            size_bytes=size_bytes,
            mime_type=mime_type,
            minio_object_name=minio_object_name,
            uploaded_by=uploaded_by,
            status=FileStatus.UPLOADING
        )
        self.db.add(file_metadata)
        self.db.commit()
        self.db.refresh(file_metadata)
        return file_metadata
    
    def get_file_metadata(self, file_id: UUID) -> Optional[FileMetadata]:
        """Get file metadata by ID."""
        return self.db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
    
    def update_file_metadata(
        self,
        file_id: UUID,
        status: Optional[FileStatus] = None,
        checksum: Optional[str] = None
    ) -> Optional[FileMetadata]:
        """Update file metadata."""
        file_metadata = self.get_file_metadata(file_id)
        if file_metadata:
            if status:
                file_metadata.status = status
                if status == FileStatus.COMPLETED:
                    file_metadata.completed_at = datetime.utcnow()
            if checksum:
                file_metadata.checksum = checksum
            self.db.commit()
            self.db.refresh(file_metadata)
        return file_metadata
    
    def create_file_chunk(
        self,
        file_id: UUID,
        chunk_number: int,
        size_bytes: int
    ) -> FileChunk:
        """Create file chunk record."""
        chunk = FileChunk(
            file_id=file_id,
            chunk_number=chunk_number,
            size_bytes=size_bytes
        )
        self.db.add(chunk)
        self.db.commit()
        self.db.refresh(chunk)
        return chunk
    
    # Auth operations
    def create_auth_session(self, user_id: int, token: UUID) -> AuthSession:
        """Create authentication session."""
        expires_at = datetime.utcnow() + timedelta(hours=settings.token_expiry_hours)
        session = AuthSession(
            token=token,
            user_id=user_id,
            expires_at=expires_at
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session
    
    def get_auth_session_by_token(self, token: UUID) -> Optional[AuthSession]:
        """Get active auth session by token."""
        now = datetime.utcnow()
        return self.db.query(AuthSession).filter(
            AuthSession.token == token,
            AuthSession.is_active == True,
            AuthSession.expires_at > now
        ).first()
    
    def deactivate_auth_session(self, token: UUID) -> None:
        """Deactivate auth session (logout)."""
        session = self.db.query(AuthSession).filter(AuthSession.token == token).first()
        if session:
            session.is_active = False
            self.db.commit()
