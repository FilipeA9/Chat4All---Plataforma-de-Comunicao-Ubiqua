"""
Integration tests for Chat4All API endpoints.
Tests authentication, conversations, and messages functionality.
"""
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from db.models import User


class TestAuthentication:
    """Tests for authentication flow."""
    
    def test_authentication_with_valid_credentials(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test POST /auth/token with valid credentials returns token."""
        response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "expires_at" in data
        assert data["username"] == "user1"
        assert data["user_id"] == seed_test_users[0].id
    
    def test_authentication_with_invalid_credentials(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test POST /auth/token with invalid credentials returns 401."""
        response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "wrongpassword"}
        )
        
        assert response.status_code == 401
        assert "detail" in response.json()
    
    def test_authentication_with_nonexistent_user(self, test_client: TestClient):
        """Test POST /auth/token with nonexistent user returns 401."""
        response = test_client.post(
            "/auth/token",
            json={"username": "nonexistent", "password": "password123"}
        )
        
        assert response.status_code == 401


class TestConversations:
    """Tests for conversation creation."""
    
    def test_create_private_conversation(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test authenticated user can create private conversation with 2 members."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Create private conversation
        response = test_client.post(
            "/v1/conversations",
            json={
                "type": "private",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "private"
        assert data["member_count"] == 2
        assert "id" in data
    
    def test_create_private_conversation_requires_exactly_two_members(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test validation enforces exactly 2 members for private conversations."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Try to create private conversation with 3 members
        response = test_client.post(
            "/v1/conversations",
            json={
                "type": "private",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id, seed_test_users[2].id]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 400
        assert "2 members" in response.json()["detail"].lower()


class TestMessages:
    """Tests for message sending and retrieval."""
    
    def test_send_text_message(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User],
        mock_kafka_producer
    ):
        """Test authenticated user can send text message to conversation."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Create conversation
        conv_response = test_client.post(
            "/v1/conversations",
            json={
                "type": "private",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        conversation_id = conv_response.json()["id"]
        
        # Send text message
        message_id = uuid4()
        response = test_client.post(
            "/v1/messages",
            json={
                "message_id": str(message_id),
                "conversation_id": conversation_id,
                "payload": {"type": "text", "content": "Hello, world!"},
                "channels": ["all"]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["message_id"] == str(message_id)
    
    def test_send_message_unauthenticated(self, test_client: TestClient):
        """Test unauthenticated request returns 401."""
        message_id = uuid4()
        response = test_client.post(
            "/v1/messages",
            json={
                "message_id": str(message_id),
                "conversation_id": 1,
                "payload": {"type": "text", "content": "Hello"},
                "channels": ["all"]
            }
        )
        
        assert response.status_code == 401
    
    def test_send_message_to_unauthorized_conversation(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test non-member cannot send to conversation (403)."""
        # User1 creates conversation with User2
        auth1_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token1 = auth1_response.json()["token"]
        
        conv_response = test_client.post(
            "/v1/conversations",
            json={
                "type": "private",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id]
            },
            headers={"Authorization": f"Bearer {token1}"}
        )
        conversation_id = conv_response.json()["id"]
        
        # User3 tries to send message to that conversation
        auth3_response = test_client.post(
            "/auth/token",
            json={"username": "user3", "password": "password123"}
        )
        token3 = auth3_response.json()["token"]
        
        message_id = uuid4()
        response = test_client.post(
            "/v1/messages",
            json={
                "message_id": str(message_id),
                "conversation_id": conversation_id,
                "payload": {"type": "text", "content": "Hello"},
                "channels": ["all"]
            },
            headers={"Authorization": f"Bearer {token3}"}
        )
        
        assert response.status_code == 403


class TestMessageRetrieval:
    """Tests for retrieving conversation messages."""
    
    def test_get_conversation_messages(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User],
        mock_kafka_producer
    ):
        """Test authenticated user can retrieve messages from conversation."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Create conversation
        conv_response = test_client.post(
            "/v1/conversations",
            json={
                "type": "private",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        conversation_id = conv_response.json()["id"]
        
        # Send a message
        message_id = uuid4()
        test_client.post(
            "/v1/messages",
            json={
                "message_id": str(message_id),
                "conversation_id": conversation_id,
                "payload": {"type": "text", "content": "Hello, world!"},
                "channels": ["all"]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Retrieve messages
        response = test_client.get(
            f"/v1/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert len(data["messages"]) >= 1
        message = data["messages"][0]
        assert message["sender_username"] == "user1"
        assert message["payload"]["type"] == "text"
        assert message["payload"]["content"] == "Hello, world!"
        assert message["status"] == "accepted"


class TestGroupConversations:
    """Tests for group conversation functionality."""
    
    def test_create_group_conversation_with_valid_members(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test group creation with 3+ members."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Create group conversation with 3 members
        response = test_client.post(
            "/v1/conversations",
            json={
                "type": "group",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id, seed_test_users[2].id],
                "name": "Test Group",
                "description": "A test group conversation"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "group"
        assert data["member_count"] == 3
        assert data["name"] == "Test Group"
        assert data["description"] == "A test group conversation"
    
    def test_create_group_conversation_enforces_minimum_members(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test validation enforces minimum 3 members for group."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Try to create group with only 2 members
        response = test_client.post(
            "/v1/conversations",
            json={
                "type": "group",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id],
                "name": "Invalid Group"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 400
        assert "at least 3 members" in response.json()["detail"].lower()
    
    def test_create_group_conversation_enforces_maximum_members(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User],
        test_db: Session
    ):
        """Test validation enforces maximum 100 members for group."""
        from db.repository import Repository
        from core.security import hash_password
        
        # Create 101 users
        repository = Repository(test_db)
        member_ids = []
        for i in range(101):
            user = repository.create_user(
                username=f"bulkuser{i}",
                password_hash=hash_password("password123"),
                full_name=f"Bulk User {i}"
            )
            member_ids.append(user.id)
        
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Try to create group with 101 members
        response = test_client.post(
            "/v1/conversations",
            json={
                "type": "group",
                "member_ids": member_ids,
                "name": "Too Large Group"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 400
        assert "100 members" in response.json()["detail"].lower()
    
    def test_all_group_members_can_retrieve_messages(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User],
        mock_kafka_producer
    ):
        """Test all members can retrieve messages from group conversation."""
        # User1 authenticates and creates group
        auth1_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token1 = auth1_response.json()["token"]
        
        conv_response = test_client.post(
            "/v1/conversations",
            json={
                "type": "group",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id, seed_test_users[2].id],
                "name": "Test Group"
            },
            headers={"Authorization": f"Bearer {token1}"}
        )
        conversation_id = conv_response.json()["id"]
        
        # User1 sends a message
        message_id = uuid4()
        test_client.post(
            "/v1/messages",
            json={
                "message_id": str(message_id),
                "conversation_id": conversation_id,
                "payload": {"type": "text", "content": "Hello group!"},
                "channels": ["all"]
            },
            headers={"Authorization": f"Bearer {token1}"}
        )
        
        # User2 can retrieve the message
        auth2_response = test_client.post(
            "/auth/token",
            json={"username": "user2", "password": "password123"}
        )
        token2 = auth2_response.json()["token"]
        
        response2 = test_client.get(
            f"/v1/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert response2.status_code == 200
        assert len(response2.json()["messages"]) >= 1
        
        # User3 can also retrieve the message
        auth3_response = test_client.post(
            "/auth/token",
            json={"username": "user3", "password": "password123"}
        )
        token3 = auth3_response.json()["token"]
        
        response3 = test_client.get(
            f"/v1/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {token3}"}
        )
        assert response3.status_code == 200
        assert len(response3.json()["messages"]) >= 1


class TestGroupMessageVisibility:
    """Tests for group message visibility and access control."""
    
    def test_message_sent_by_one_member_visible_to_all(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User],
        mock_kafka_producer
    ):
        """Test message sent by one member is visible to all members."""
        # User1 creates group
        auth1_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token1 = auth1_response.json()["token"]
        
        conv_response = test_client.post(
            "/v1/conversations",
            json={
                "type": "group",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id, seed_test_users[2].id],
                "name": "Visibility Test Group"
            },
            headers={"Authorization": f"Bearer {token1}"}
        )
        conversation_id = conv_response.json()["id"]
        
        # User2 sends a message
        auth2_response = test_client.post(
            "/auth/token",
            json={"username": "user2", "password": "password123"}
        )
        token2 = auth2_response.json()["token"]
        
        message_id = uuid4()
        test_client.post(
            "/v1/messages",
            json={
                "message_id": str(message_id),
                "conversation_id": conversation_id,
                "payload": {"type": "text", "content": "Message from User2"},
                "channels": ["all"]
            },
            headers={"Authorization": f"Bearer {token2}"}
        )
        
        # User1 and User3 can both see the message
        response1 = test_client.get(
            f"/v1/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {token1}"}
        )
        assert response1.status_code == 200
        messages = response1.json()["messages"]
        assert any(m["sender_username"] == "user2" for m in messages)
        
        auth3_response = test_client.post(
            "/auth/token",
            json={"username": "user3", "password": "password123"}
        )
        token3 = auth3_response.json()["token"]
        
        response3 = test_client.get(
            f"/v1/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {token3}"}
        )
        assert response3.status_code == 200
        messages = response3.json()["messages"]
        assert any(m["sender_username"] == "user2" for m in messages)
    
    def test_non_member_cannot_access_group_messages(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test non-member cannot access group messages (403)."""
        # User1 creates group with User2 and User3 (User4 is NOT a member)
        auth1_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token1 = auth1_response.json()["token"]
        
        conv_response = test_client.post(
            "/v1/conversations",
            json={
                "type": "group",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id, seed_test_users[2].id],
                "name": "Private Group"
            },
            headers={"Authorization": f"Bearer {token1}"}
        )
        conversation_id = conv_response.json()["id"]
        
        # User4 (non-member) tries to access messages
        auth4_response = test_client.post(
            "/auth/token",
            json={"username": "user4", "password": "password123"}
        )
        token4 = auth4_response.json()["token"]
        
        response = test_client.get(
            f"/v1/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {token4}"}
        )
        
        assert response.status_code == 403
        assert "not a member" in response.json()["detail"].lower()


class TestFileUploadInitiate:
    """Tests for file upload initiation."""
    
    def test_file_upload_initiate_returns_presigned_url(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test POST /v1/files/initiate returns file_id and presigned URL."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Initiate file upload
        response = test_client.post(
            "/v1/files/initiate",
            json={
                "filename": "test_document.pdf",
                "size_bytes": 1024000,  # 1MB
                "mime_type": "application/pdf"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "file_id" in data
        assert "upload_url" in data
        assert "expires_at" in data
        assert data["upload_url"].startswith("http")
    
    def test_file_upload_rejects_oversized_files(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test file size validation rejects files > 2GB (413 error)."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Try to initiate upload for 3GB file
        response = test_client.post(
            "/v1/files/initiate",
            json={
                "filename": "huge_file.zip",
                "size_bytes": 3_221_225_472,  # 3GB
                "mime_type": "application/zip"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 413
        assert "2gb" in response.json()["detail"].lower() or "too large" in response.json()["detail"].lower()


class TestFileUploadComplete:
    """Tests for completing file upload."""
    
    def test_file_upload_complete_with_valid_checksum(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test POST /v1/files/complete with valid checksum marks file as completed."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Initiate upload
        init_response = test_client.post(
            "/v1/files/initiate",
            json={
                "filename": "test_file.txt",
                "size_bytes": 1024,
                "mime_type": "text/plain"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        file_id = init_response.json()["file_id"]
        
        # Complete upload with checksum
        complete_response = test_client.post(
            "/v1/files/complete",
            json={
                "file_id": file_id,
                "checksum": "a" * 64  # Valid SHA-256 format
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert complete_response.status_code == 200
        data = complete_response.json()
        assert data["file_id"] == file_id
        assert data["status"] == "completed"
        assert "download_url" in data
    
    def test_file_upload_complete_with_invalid_checksum(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test POST /v1/files/complete with invalid checksum returns 400 error."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Initiate upload
        init_response = test_client.post(
            "/v1/files/initiate",
            json={
                "filename": "test_file.txt",
                "size_bytes": 1024,
                "mime_type": "text/plain"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        file_id = init_response.json()["file_id"]
        
        # Try to complete with invalid checksum format
        complete_response = test_client.post(
            "/v1/files/complete",
            json={
                "file_id": file_id,
                "checksum": "invalid"  # Too short, not SHA-256
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert complete_response.status_code == 422  # Pydantic validation error


class TestFileMessages:
    """Tests for sending file messages."""
    
    def test_send_file_message_with_valid_file_id(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User],
        mock_kafka_producer
    ):
        """Test user can send message with payload type='file' and valid file_id."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Create conversation
        conv_response = test_client.post(
            "/v1/conversations",
            json={
                "type": "private",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        conversation_id = conv_response.json()["id"]
        
        # Initiate and complete file upload
        init_response = test_client.post(
            "/v1/files/initiate",
            json={
                "filename": "document.pdf",
                "size_bytes": 5000,
                "mime_type": "application/pdf"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        file_id = init_response.json()["file_id"]
        
        test_client.post(
            "/v1/files/complete",
            json={
                "file_id": file_id,
                "checksum": "b" * 64
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Send file message
        message_id = uuid4()
        response = test_client.post(
            "/v1/messages",
            json={
                "message_id": str(message_id),
                "conversation_id": conversation_id,
                "payload": {"type": "file", "file_id": file_id},
                "channels": ["all"]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 202
        assert response.json()["status"] == "accepted"
    
    def test_send_file_message_with_invalid_file_id(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User]
    ):
        """Test message with invalid file_id returns 400 error."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Create conversation
        conv_response = test_client.post(
            "/v1/conversations",
            json={
                "type": "private",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        conversation_id = conv_response.json()["id"]
        
        # Try to send file message with non-existent file_id
        message_id = uuid4()
        fake_file_id = str(uuid4())
        response = test_client.post(
            "/v1/messages",
            json={
                "message_id": str(message_id),
                "conversation_id": conversation_id,
                "payload": {"type": "file", "file_id": fake_file_id},
                "channels": ["all"]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 400
        assert "file not found" in response.json()["detail"].lower()


class TestMultiChannelRouting:
    """Tests for multi-channel message routing."""
    
    def test_single_channel_routing_whatsapp_only(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User],
        mock_kafka_producer,
        test_db: Session
    ):
        """Test message with channels=['whatsapp'] routes only to WhatsApp mock."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Create conversation
        conv_response = test_client.post(
            "/v1/conversations",
            json={
                "type": "private",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        conversation_id = conv_response.json()["id"]
        
        # Send message to WhatsApp only
        message_id = uuid4()
        response = test_client.post(
            "/v1/messages",
            json={
                "message_id": str(message_id),
                "conversation_id": conversation_id,
                "payload": {"type": "text", "content": "WhatsApp only message"},
                "channels": ["whatsapp"]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 202
        
        # Verify message was published to Kafka
        assert len(mock_kafka_producer.published_messages) > 0
        kafka_message = mock_kafka_producer.published_messages[-1]
        assert kafka_message["topic"] == "message_processing"
        assert kafka_message["message"]["channels"] == ["whatsapp"]
    
    def test_multi_channel_routing_both_channels(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User],
        mock_kafka_producer
    ):
        """Test message with channels=['whatsapp', 'instagram'] routes to both mocks."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Create conversation
        conv_response = test_client.post(
            "/v1/conversations",
            json={
                "type": "private",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        conversation_id = conv_response.json()["id"]
        
        # Send message to both channels
        message_id = uuid4()
        response = test_client.post(
            "/v1/messages",
            json={
                "message_id": str(message_id),
                "conversation_id": conversation_id,
                "payload": {"type": "text", "content": "Multi-channel message"},
                "channels": ["whatsapp", "instagram"]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 202
        
        # Verify message includes both channels
        kafka_message = mock_kafka_producer.published_messages[-1]
        assert kafka_message["message"]["channels"] == ["whatsapp", "instagram"]
    
    def test_all_channels_routing(
        self, 
        test_client: TestClient, 
        seed_test_users: list[User],
        mock_kafka_producer
    ):
        """Test message with channels=['all'] routes to all available mock connectors."""
        # Authenticate
        auth_response = test_client.post(
            "/auth/token",
            json={"username": "user1", "password": "password123"}
        )
        token = auth_response.json()["token"]
        
        # Create conversation
        conv_response = test_client.post(
            "/v1/conversations",
            json={
                "type": "private",
                "member_ids": [seed_test_users[0].id, seed_test_users[1].id]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        conversation_id = conv_response.json()["id"]
        
        # Send message to all channels
        message_id = uuid4()
        response = test_client.post(
            "/v1/messages",
            json={
                "message_id": str(message_id),
                "conversation_id": conversation_id,
                "payload": {"type": "text", "content": "Broadcast message"},
                "channels": ["all"]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 202
        
        # Verify message includes "all" channel
        kafka_message = mock_kafka_producer.published_messages[-1]
        assert kafka_message["message"]["channels"] == ["all"]
        assert kafka_message["message"]["payload"]["content"] == "Broadcast message"
