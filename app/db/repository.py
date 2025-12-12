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
    File, FileChunkModel, AuthSession, ConversationType, MessageStatus, FileStatus,
    OutboxEvent
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
    
    def mark_conversation_as_read(self, conversation_id: int, user_id: int) -> int:
        """
        Mark all messages in a conversation as READ for a specific user.
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID marking messages as read
            
        Returns:
            Number of messages marked as read
        """
        # Update all messages in the conversation to READ status
        # In a full implementation, this would update a separate read_receipts table
        # For now, we'll update the message status field
        updated_count = self.db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.status != MessageStatus.READ
        ).update({
            'status': MessageStatus.READ,
            'updated_at': datetime.utcnow()
        }, synchronize_session=False)
        
        self.db.commit()
        return updated_count
    
    # File operations
    def create_file_metadata(
        self,
        file_id: UUID,
        filename: str,
        size_bytes: int,
        mime_type: str,
        minio_object_name: str,
        uploaded_by: int
    ) -> File:
        """Create file metadata record."""
        file_metadata = File(
            id=file_id,
            filename=filename,
            file_size=size_bytes,
            mime_type=mime_type,
            storage_key=minio_object_name,
            uploader_id=uploaded_by,
            conversation_id=1,  # Default to conversation 1 for compatibility
            status=FileStatus.PENDING,
            chunk_size=5242880,  # 5MB
            total_chunks=1
        )
        self.db.add(file_metadata)
        self.db.commit()
        self.db.refresh(file_metadata)
        return file_metadata
    
    def get_file_metadata(self, file_id: UUID) -> Optional[File]:
        """Get file metadata by ID."""
        return self.db.query(File).filter(File.id == file_id).first()
    
    def update_file_metadata(
        self,
        file_id: UUID,
        status: Optional[FileStatus] = None,
        checksum: Optional[str] = None
    ) -> Optional[File]:
        """Update file metadata."""
        file_metadata = self.get_file_metadata(file_id)
        if file_metadata:
            if status:
                file_metadata.status = status
                if status == FileStatus.COMPLETED:
                    file_metadata.completed_at = datetime.utcnow()
            if checksum:
                file_metadata.checksum_sha256 = checksum
            self.db.commit()
            self.db.refresh(file_metadata)
        return file_metadata
    
    def create_file_chunk(
        self,
        file_id: UUID,
        chunk_number: int,
        size_bytes: int
    ) -> FileChunkModel:
        """Create file chunk record."""
        chunk = FileChunkModel(
            file_id=file_id,
            chunk_number=chunk_number,
            chunk_size=size_bytes,
            storage_key=f"chunks/{file_id}/chunk-{chunk_number:03d}"
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
    
    # Outbox operations (Transactional Outbox pattern)
    def create_outbox_event(
        self,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        payload: dict
    ) -> OutboxEvent:
        """
        Create outbox event for reliable Kafka publishing.
        
        This method is called within the same transaction as domain entity creation
        (e.g., message creation) to implement the Transactional Outbox pattern.
        The OutboxPoller worker will poll unpublished events and publish to Kafka.
        
        Args:
            aggregate_type: Type of domain entity ('message', 'conversation', 'file')
            aggregate_id: UUID of the domain entity
            event_type: Event type (e.g., 'message.created', 'file.uploaded')
            payload: Complete event data as dict (will be stored as JSONB)
            
        Returns:
            OutboxEvent: Created outbox event (not yet published)
        """
        outbox_event = OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            published=False,
            version=1
        )
        self.db.add(outbox_event)
        # Note: Do NOT commit here - let the caller control transaction boundary
        return outbox_event
    
    def get_unpublished_outbox_events(self, limit: int = 100) -> List[OutboxEvent]:
        """
        Get unpublished outbox events for polling.
        
        Used by OutboxPoller worker to fetch events that need to be published to Kafka.
        Orders by created_at to ensure FIFO processing.
        
        Args:
            limit: Maximum number of events to fetch per poll
            
        Returns:
            List of unpublished outbox events
        """
        return self.db.query(OutboxEvent).filter(
            OutboxEvent.published == False
        ).order_by(OutboxEvent.created_at).limit(limit).all()
    
    def mark_outbox_event_published(self, event_id: UUID) -> Optional[OutboxEvent]:
        """
        Mark outbox event as successfully published to Kafka.
        
        Called by OutboxPoller worker after successful Kafka publish.
        
        Args:
            event_id: UUID of the outbox event
            
        Returns:
            Updated outbox event or None if not found
        """
        event = self.db.query(OutboxEvent).filter(OutboxEvent.id == event_id).first()
        if event:
            event.published = True
            event.published_at = datetime.utcnow()
            event.error_message = None  # Clear any previous error
            self.db.commit()
            self.db.refresh(event)
        return event
    
    def mark_outbox_event_failed(
        self, 
        event_id: UUID, 
        error_message: str
    ) -> Optional[OutboxEvent]:
        """
        Mark outbox event as failed after retry exhaustion.
        
        Increments version counter for exponential backoff and stores error message.
        
        Args:
            event_id: UUID of the outbox event
            error_message: Error description from Kafka publish attempt
            
        Returns:
            Updated outbox event or None if not found
        """
        event = self.db.query(OutboxEvent).filter(OutboxEvent.id == event_id).first()
        if event:
            event.version += 1
            event.error_message = error_message
            self.db.commit()
            self.db.refresh(event)
        return event
