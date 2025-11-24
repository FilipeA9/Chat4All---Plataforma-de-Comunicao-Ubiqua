"""
Unit tests for database models.
Tests model validation, relationships, and business logic.
"""
import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import (
    Base, User, Conversation, ConversationMember, Message,
    MessageStatusHistory, FileMetadata, FileChunk, AuthSession,
    ConversationType, MessageStatus, FileStatus
)
from core.security import hash_password, verify_password


# Create in-memory test database
@pytest.fixture
def test_db_session():
    """Create a test database session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)
    session = TestSessionLocal()
    yield session
    session.close()


class TestUserModel:
    """Tests for User model."""
    
    def test_user_password_hashing(self):
        """Test that password is properly hashed."""
        plain_password = "test_password_123"
        hashed = hash_password(plain_password)
        
        # Hashed password should not equal plain password
        assert hashed != plain_password
        
        # Hashed password should be verifiable
        assert verify_password(plain_password, hashed)
        
        # Wrong password should not verify
        assert not verify_password("wrong_password", hashed)
    
    def test_user_creation(self, test_db_session):
        """Test creating a user with all required fields."""
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash=hash_password("password123"),
            full_name="Test User"
        )
        test_db_session.add(user)
        test_db_session.commit()
        
        # Verify user was created
        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"
        assert user.created_at is not None
        assert isinstance(user.created_at, datetime)
    
    def test_user_unique_username(self, test_db_session):
        """Test that username must be unique."""
        user1 = User(
            username="duplicate",
            email="user1@example.com",
            password_hash=hash_password("password"),
            full_name="User 1"
        )
        test_db_session.add(user1)
        test_db_session.commit()
        
        # Try to create user with same username
        user2 = User(
            username="duplicate",
            email="user2@example.com",
            password_hash=hash_password("password"),
            full_name="User 2"
        )
        test_db_session.add(user2)
        
        # Should raise integrity error
        with pytest.raises(Exception):
            test_db_session.commit()


class TestConversationModel:
    """Tests for Conversation model."""
    
    def test_conversation_type_enum(self, test_db_session):
        """Test conversation type ENUM validation."""
        # Test valid private conversation
        conv_private = Conversation(
            type=ConversationType.PRIVATE,
            name=None,
            description=None
        )
        test_db_session.add(conv_private)
        test_db_session.commit()
        assert conv_private.type == ConversationType.PRIVATE
        
        # Test valid group conversation
        conv_group = Conversation(
            type=ConversationType.GROUP,
            name="Test Group",
            description="A test group conversation"
        )
        test_db_session.add(conv_group)
        test_db_session.commit()
        assert conv_group.type == ConversationType.GROUP
    
    def test_conversation_timestamps(self, test_db_session):
        """Test conversation automatic timestamps."""
        conversation = Conversation(
            type=ConversationType.PRIVATE
        )
        test_db_session.add(conversation)
        test_db_session.commit()
        
        # Verify timestamps are set
        assert conversation.created_at is not None
        assert isinstance(conversation.created_at, datetime)


class TestMessageModel:
    """Tests for Message model."""
    
    def test_message_status_enum(self, test_db_session):
        """Test message status ENUM types."""
        # Create test user and conversation
        user = User(
            username="sender",
            email="sender@example.com",
            password_hash=hash_password("password"),
            full_name="Sender"
        )
        conversation = Conversation(type=ConversationType.PRIVATE)
        test_db_session.add(user)
        test_db_session.add(conversation)
        test_db_session.commit()
        
        # Test all valid message statuses
        statuses = [MessageStatus.ACCEPTED, MessageStatus.DELIVERED, MessageStatus.FAILED]
        
        for status in statuses:
            message = Message(
                id=uuid4(),
                conversation_id=conversation.id,
                sender_id=user.id,
                payload={"type": "text", "content": "Test"},
                status=status,
                channels=["whatsapp"]
            )
            test_db_session.add(message)
            test_db_session.commit()
            assert message.status == status
    
    def test_message_payload_validation(self, test_db_session):
        """Test message payload field accepts JSON."""
        user = User(
            username="sender",
            email="sender@example.com",
            password_hash=hash_password("password"),
            full_name="Sender"
        )
        conversation = Conversation(type=ConversationType.PRIVATE)
        test_db_session.add(user)
        test_db_session.add(conversation)
        test_db_session.commit()
        
        # Test text payload
        text_message = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            sender_id=user.id,
            payload={"type": "text", "content": "Hello, world!"},
            status=MessageStatus.ACCEPTED,
            channels=["whatsapp"]
        )
        test_db_session.add(text_message)
        test_db_session.commit()
        
        assert text_message.payload["type"] == "text"
        assert text_message.payload["content"] == "Hello, world!"
        
        # Test file payload
        file_message = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            sender_id=user.id,
            payload={"type": "file", "file_id": str(uuid4())},
            status=MessageStatus.ACCEPTED,
            channels=["instagram"]
        )
        test_db_session.add(file_message)
        test_db_session.commit()
        
        assert file_message.payload["type"] == "file"
        assert "file_id" in file_message.payload
    
    def test_message_channels_list(self, test_db_session):
        """Test message channels field accepts list."""
        user = User(
            username="sender",
            email="sender@example.com",
            password_hash=hash_password("password"),
            full_name="Sender"
        )
        conversation = Conversation(type=ConversationType.PRIVATE)
        test_db_session.add(user)
        test_db_session.add(conversation)
        test_db_session.commit()
        
        # Test single channel
        message1 = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            sender_id=user.id,
            payload={"type": "text", "content": "Test"},
            status=MessageStatus.ACCEPTED,
            channels=["whatsapp"]
        )
        test_db_session.add(message1)
        test_db_session.commit()
        assert message1.channels == ["whatsapp"]
        
        # Test multiple channels
        message2 = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            sender_id=user.id,
            payload={"type": "text", "content": "Test"},
            status=MessageStatus.ACCEPTED,
            channels=["whatsapp", "instagram"]
        )
        test_db_session.add(message2)
        test_db_session.commit()
        assert message2.channels == ["whatsapp", "instagram"]
        
        # Test "all" channel
        message3 = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            sender_id=user.id,
            payload={"type": "text", "content": "Test"},
            status=MessageStatus.ACCEPTED,
            channels=["all"]
        )
        test_db_session.add(message3)
        test_db_session.commit()
        assert message3.channels == ["all"]


class TestFileMetadataModel:
    """Tests for FileMetadata model."""
    
    def test_file_status_enum(self, test_db_session):
        """Test file status ENUM types."""
        user = User(
            username="uploader",
            email="uploader@example.com",
            password_hash=hash_password("password"),
            full_name="Uploader"
        )
        test_db_session.add(user)
        test_db_session.commit()
        
        # Test all valid file statuses
        statuses = [FileStatus.UPLOADING, FileStatus.COMPLETED, FileStatus.FAILED]
        
        for status in statuses:
            file_metadata = FileMetadata(
                id=uuid4(),
                filename="test.pdf",
                size_bytes=1024,
                mime_type="application/pdf",
                minio_object_name=f"uploads/{user.id}/test.pdf",
                uploaded_by=user.id,
                status=status
            )
            test_db_session.add(file_metadata)
            test_db_session.commit()
            assert file_metadata.status == status
    
    def test_file_metadata_creation(self, test_db_session):
        """Test creating file metadata with all fields."""
        user = User(
            username="uploader",
            email="uploader@example.com",
            password_hash=hash_password("password"),
            full_name="Uploader"
        )
        test_db_session.add(user)
        test_db_session.commit()
        
        file_id = uuid4()
        file_metadata = FileMetadata(
            id=file_id,
            filename="document.pdf",
            size_bytes=5242880,
            mime_type="application/pdf",
            minio_object_name=f"uploads/{user.id}/{file_id}/document.pdf",
            uploaded_by=user.id,
            status=FileStatus.UPLOADING,
            checksum=None
        )
        test_db_session.add(file_metadata)
        test_db_session.commit()
        
        assert file_metadata.id == file_id
        assert file_metadata.filename == "document.pdf"
        assert file_metadata.size_bytes == 5242880
        assert file_metadata.mime_type == "application/pdf"
        assert file_metadata.status == FileStatus.UPLOADING
        assert file_metadata.created_at is not None


class TestAuthSessionModel:
    """Tests for AuthSession model."""
    
    def test_auth_session_expiry(self, test_db_session):
        """Test auth session with expiry timestamp."""
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash=hash_password("password"),
            full_name="Test User"
        )
        test_db_session.add(user)
        test_db_session.commit()
        
        token = uuid4()
        expires_at = datetime.utcnow() + timedelta(hours=24)
        
        auth_session = AuthSession(
            user_id=user.id,
            token=token,
            expires_at=expires_at
        )
        test_db_session.add(auth_session)
        test_db_session.commit()
        
        assert auth_session.token == token
        assert auth_session.user_id == user.id
        assert auth_session.expires_at == expires_at
        assert auth_session.created_at is not None
    
    def test_auth_session_is_expired(self, test_db_session):
        """Test checking if auth session is expired."""
        user = User(
            username="testuser",
            email="test@example.com",
            password_hash=hash_password("password"),
            full_name="Test User"
        )
        test_db_session.add(user)
        test_db_session.commit()
        
        # Create expired session
        expired_session = AuthSession(
            user_id=user.id,
            token=uuid4(),
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        test_db_session.add(expired_session)
        test_db_session.commit()
        
        # Verify session is expired
        assert expired_session.expires_at < datetime.utcnow()
        
        # Create valid session
        valid_session = AuthSession(
            user_id=user.id,
            token=uuid4(),
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        test_db_session.add(valid_session)
        test_db_session.commit()
        
        # Verify session is not expired
        assert valid_session.expires_at > datetime.utcnow()


class TestRelationships:
    """Tests for model relationships."""
    
    def test_conversation_members_relationship(self, test_db_session):
        """Test conversation and members many-to-many relationship."""
        # Create users
        user1 = User(
            username="user1",
            email="user1@example.com",
            password_hash=hash_password("password"),
            full_name="User 1"
        )
        user2 = User(
            username="user2",
            email="user2@example.com",
            password_hash=hash_password("password"),
            full_name="User 2"
        )
        test_db_session.add(user1)
        test_db_session.add(user2)
        test_db_session.commit()
        
        # Create conversation
        conversation = Conversation(type=ConversationType.PRIVATE)
        test_db_session.add(conversation)
        test_db_session.commit()
        
        # Add members
        member1 = ConversationMember(
            conversation_id=conversation.id,
            user_id=user1.id
        )
        member2 = ConversationMember(
            conversation_id=conversation.id,
            user_id=user2.id
        )
        test_db_session.add(member1)
        test_db_session.add(member2)
        test_db_session.commit()
        
        # Verify relationships
        assert len(conversation.members) == 2
        assert member1 in conversation.members
        assert member2 in conversation.members
    
    def test_message_status_history_relationship(self, test_db_session):
        """Test message and status history one-to-many relationship."""
        # Create user and conversation
        user = User(
            username="sender",
            email="sender@example.com",
            password_hash=hash_password("password"),
            full_name="Sender"
        )
        conversation = Conversation(type=ConversationType.PRIVATE)
        test_db_session.add(user)
        test_db_session.add(conversation)
        test_db_session.commit()
        
        # Create message
        message = Message(
            id=uuid4(),
            conversation_id=conversation.id,
            sender_id=user.id,
            payload={"type": "text", "content": "Test"},
            status=MessageStatus.ACCEPTED,
            channels=["whatsapp"]
        )
        test_db_session.add(message)
        test_db_session.commit()
        
        # Add status history
        history1 = MessageStatusHistory(
            message_id=message.id,
            status=MessageStatus.ACCEPTED,
            channel="whatsapp"
        )
        history2 = MessageStatusHistory(
            message_id=message.id,
            status=MessageStatus.DELIVERED,
            channel="whatsapp"
        )
        test_db_session.add(history1)
        test_db_session.add(history2)
        test_db_session.commit()
        
        # Verify relationship
        assert len(message.status_history) == 2
        assert history1 in message.status_history
        assert history2 in message.status_history
