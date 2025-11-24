"""
Pytest configuration and fixtures for testing.
Provides test database, test client, and other shared fixtures.
"""
import pytest
from typing import Generator
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient
from db.database import Base
from db.models import User
from db.repository import Repository
from core.security import hash_password
from main import app
from api.dependencies import get_db


# Test database URL (use in-memory SQLite for tests)
TEST_DATABASE_URL = "sqlite:///./test_chat4all.db"

# Create test engine
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """
    Create a fresh database for each test.
    Automatically creates and destroys tables.
    """
    # Create tables
    Base.metadata.create_all(bind=test_engine)
    
    # Create session
    db = TestSessionLocal()
    
    try:
        yield db
    finally:
        db.close()
        # Drop tables after test
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def test_client(test_db: Session) -> TestClient:
    """
    Create a test client with test database dependency override.
    """
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    client = TestClient(app)
    yield client
    
    # Clean up dependency overrides
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def seed_test_users(test_db: Session) -> list[User]:
    """
    Seed test database with 5 test users.
    Returns list of created users.
    """
    repository = Repository(test_db)
    users = []
    
    for i in range(1, 6):
        user = repository.create_user(
            username=f"user{i}",
            password_hash=hash_password("password123"),
            full_name=f"Test User {i}"
        )
        users.append(user)
    
    return users


@pytest.fixture
def mock_kafka_producer(monkeypatch):
    """
    Mock Kafka producer for testing without real Kafka connection.
    """
    class MockKafkaProducer:
        def __init__(self):
            self.published_messages = []
        
        def publish_message(self, topic: str, message: dict) -> bool:
            self.published_messages.append({"topic": topic, "message": message})
            return True
        
        def close(self):
            pass
    
    mock_producer = MockKafkaProducer()
    
    # Mock the get_kafka_producer function
    import services.kafka_producer
    monkeypatch.setattr(services.kafka_producer, "_kafka_producer", mock_producer)
    monkeypatch.setattr(services.kafka_producer, "get_kafka_producer", lambda: mock_producer)
    
    return mock_producer
