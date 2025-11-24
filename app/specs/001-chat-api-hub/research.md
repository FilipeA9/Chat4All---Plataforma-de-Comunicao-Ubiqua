# Research: Chat4All API Hub

**Phase**: 0 - Outline & Research  
**Created**: 2025-11-24  
**Purpose**: Resolve technical unknowns and establish best practices for implementation

## Overview

This document consolidates research findings for the Chat4All API implementation. Since the project has a well-defined technical stack (per constitution), this phase focuses on best practices, integration patterns, and addressing specific technical challenges.

## Research Areas

### 1. FastAPI Best Practices for Async Message Processing

**Decision**: Use FastAPI with BackgroundTasks for non-blocking Kafka publishing

**Rationale**: 
- FastAPI's `BackgroundTasks` allows the API to return HTTP 200 immediately while publishing to Kafka happens asynchronously
- This pattern satisfies the requirement for <500ms response time
- Alternative considered: Synchronous Kafka publish would block the response and violate performance constraints

**Implementation Pattern**:
```python
from fastapi import BackgroundTasks

async def publish_to_kafka_background(message: dict):
    # Called after response sent
    kafka_producer.send("message_processing", message)

@app.post("/v1/messages")
async def send_message(message: MessageCreate, background_tasks: BackgroundTasks):
    # Store in DB with status="accepted"
    db_message = save_message(message)
    # Queue kafka publish for after response
    background_tasks.add_task(publish_to_kafka_background, db_message)
    return {"status": "accepted", "message_id": message.message_id}
```

### 2. PostgreSQL Schema Design for Message Status Tracking

**Decision**: Use ENUM types for status and conversation type, JSONB for flexible payloads

**Rationale**:
- PostgreSQL ENUM provides type safety and better performance than VARCHAR checks
- JSONB allows flexible message payload structure (text vs file) without schema changes
- Separate MessageStatus table provides audit trail (constitutional requirement FR-041)

**Schema Highlights**:
```sql
CREATE TYPE conversation_type AS ENUM ('private', 'group');
CREATE TYPE message_status AS ENUM ('accepted', 'in_transit', 'delivered', 'failed');

CREATE TABLE messages (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id),
    from_user_id UUID REFERENCES users(id),
    payload JSONB NOT NULL,  -- {type: "text", text: "..."} or {type: "file", file_id: "..."}
    status message_status DEFAULT 'accepted',
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Alternatives Considered**:
- Separate tables for text_messages and file_messages → Rejected: Increases complexity, harder to query conversation history
- VARCHAR for status → Rejected: No type safety, allows invalid values

### 3. Kafka Topic Strategy

**Decision**: 3-topic pattern with fan-out routing

**Rationale**:
- `message_processing`: Main topic where API publishes all messages
- `whatsapp_outgoing`, `instagram_outgoing`: Channel-specific topics
- Message router worker acts as intelligent fan-out, routing based on `channels` field

**Topic Structure**:
```
API → message_processing → message_router → ┬→ whatsapp_outgoing → whatsapp_mock
                                             └→ instagram_outgoing → instagram_mock
```

**Why Not Direct Publishing**: 
- API remains channel-agnostic (doesn't know about WhatsApp/Instagram topics)
- Easy to add new channels without changing API code
- Router can implement complex routing logic (e.g., "all" = both channels)

**Configuration**:
- Single partition per topic (sufficient for POC, simplifies ordering guarantees)
- Replication factor: 1 (local development)
- Consumer groups: One per worker type (message_router, whatsapp_mock, instagram_mock)

### 4. MinIO Chunked Upload Pattern

**Decision**: 3-phase upload with presigned URLs

**Rationale**:
- **Phase 1 (Initiate)**: API generates file_id, creates DB record, returns presigned URL
- **Phase 2 (Upload Chunks)**: Client uploads directly to MinIO using presigned URLs (bypasses API for large data transfer)
- **Phase 3 (Complete)**: API validates checksum and marks file complete

**Why Presigned URLs**: 
- Reduces API server load (large files don't flow through FastAPI)
- MinIO handles multipart upload complexity
- Client gets direct S3-compatible upload speed

**Implementation Pattern**:
```python
# Phase 1: Initiate
@app.post("/v1/files/initiate")
async def initiate_upload(filename: str, size: int):
    file_id = uuid4()
    # Create DB record
    file_record = FileMetadata(id=file_id, filename=filename, size=size, status="uploading")
    db.add(file_record)
    
    # Generate presigned URL (valid for 1 hour)
    presigned_url = minio_client.presigned_put_object(
        bucket_name="chat4all-files",
        object_name=f"{file_id}/chunk_0",
        expires=timedelta(hours=1)
    )
    return {"file_id": file_id, "upload_url": presigned_url}

# Phase 3: Complete
@app.post("/v1/files/complete")
async def complete_upload(file_id: UUID, checksum: str):
    # Verify file in MinIO
    object_stat = minio_client.stat_object("chat4all-files", str(file_id))
    calculated_checksum = calculate_checksum(object_stat)
    
    if calculated_checksum != checksum:
        raise HTTPException(400, "Checksum mismatch")
    
    # Update DB
    db.query(FileMetadata).filter_by(id=file_id).update({"status": "completed"})
    return {"status": "completed"}
```

**Alternatives Considered**:
- Direct upload through API → Rejected: Would require buffering 2GB in memory, violates constraints
- Streaming upload → Considered: More complex, presigned URLs are simpler for POC

### 5. Authentication Mechanism

**Decision**: Simple token-based authentication with session storage

**Rationale**:
- Constitution explicitly mandates simplicity (Principle VI)
- No JWT complexity needed for academic POC
- Token stored in database, validated on each request

**Implementation**:
```python
# Token generation (POST /auth/token)
def authenticate_user(username: str, password: str) -> User:
    user = db.query(User).filter_by(username=username).first()
    if not user or not bcrypt.checkpw(password.encode(), user.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    
    # Generate simple token (random UUID)
    token = str(uuid4())
    session = AuthSession(user_id=user.id, token=token, expires_at=datetime.now() + timedelta(hours=1))
    db.add(session)
    return {"access_token": token, "expires_in": 3600}

# Token validation (dependency injection)
async def get_current_user(token: str = Header(..., alias="Authorization")) -> User:
    session = db.query(AuthSession).filter_by(token=token).first()
    if not session or session.expires_at < datetime.now():
        raise HTTPException(401, "Invalid or expired token")
    return session.user
```

**Why Not JWT**: 
- Adds complexity (signing, verification, libraries)
- Requires secret key management
- Database lookup happens anyway for user data
- Constitution Principle VI: "Simple username/password authentication with bcrypt hashing is sufficient"

### 6. SQLAlchemy Repository Pattern

**Decision**: Use repository layer (`db/repository.py`) for all database operations

**Rationale**:
- Constitution Principle II mandates "data repositories (SQLAlchemy ORM)"
- Separates business logic from data access
- Makes testing easier (can mock repository instead of database)

**Pattern**:
```python
# db/repository.py
class MessageRepository:
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def create_message(self, message: MessageCreate) -> Message:
        db_message = Message(**message.dict())
        self.db.add(db_message)
        self.db.commit()
        return db_message
    
    def get_conversation_messages(self, conversation_id: UUID) -> List[Message]:
        return self.db.query(Message).filter_by(conversation_id=conversation_id).all()
    
    def update_message_status(self, message_id: UUID, status: str):
        self.db.query(Message).filter_by(id=message_id).update({"status": status})
        self.db.commit()

# Usage in API
@app.get("/v1/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: UUID, repo: MessageRepository = Depends(get_repository)):
    return repo.get_conversation_messages(conversation_id)
```

### 7. Worker Process Architecture

**Decision**: Separate Python processes for each worker type, using kafka-python consumer

**Rationale**:
- Each worker is an independent Python script executed via `python -m workers.message_router`
- Workers run in infinite loops consuming from Kafka
- Graceful shutdown on SIGINT/SIGTERM

**Worker Template**:
```python
# workers/message_router.py
from kafka import KafkaConsumer
import json
import signal
import sys

def signal_handler(sig, frame):
    print("Shutting down message router...")
    consumer.close()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

consumer = KafkaConsumer(
    'message_processing',
    bootstrap_servers=['localhost:9092'],
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    group_id='message-router-group'
)

print("Message router started, consuming from message_processing topic...")

for message in consumer:
    msg_data = message.value
    channels = msg_data.get('channels', [])
    
    if 'all' in channels or 'whatsapp' in channels:
        publish_to_topic('whatsapp_outgoing', msg_data)
    
    if 'all' in channels or 'instagram' in channels:
        publish_to_topic('instagram_outgoing', msg_data)
```

**Execution Strategy**:
```bash
# Terminal 1: Start API
python main.py

# Terminal 2: Start message router
python -m workers.message_router

# Terminal 3: Start WhatsApp mock
python -m workers.whatsapp_mock

# Terminal 4: Start Instagram mock
python -m workers.instagram_mock
```

### 8. Testing Strategy

**Decision**: pytest with separate test files for integration and unit tests

**Test Organization**:
```
tests/
├── conftest.py           # Fixtures: test_db, test_client, mock_kafka, mock_minio
├── test_api.py           # Integration tests (full request/response cycles)
├── test_workers.py       # Unit tests (worker logic without Kafka)
└── test_models.py        # Unit tests (ORM model behavior)
```

**Key Fixtures**:
```python
# conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def test_db():
    engine = create_engine("postgresql://test:test@localhost/chat4all_test")
    TestingSessionLocal = sessionmaker(bind=engine)
    # Create tables
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    # Cleanup
    db.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def test_client(test_db):
    app.dependency_overrides[get_db] = lambda: test_db
    client = TestClient(app)
    return client
```

**Integration Test Example**:
```python
# test_api.py
def test_send_message_flow(test_client):
    # Authenticate
    response = test_client.post("/auth/token", json={"username": "user1", "password": "pass1"})
    token = response.json()["access_token"]
    
    # Create conversation
    response = test_client.post(
        "/v1/conversations",
        json={"type": "private", "members": ["user1_id", "user2_id"]},
        headers={"Authorization": token}
    )
    conv_id = response.json()["conversation_id"]
    
    # Send message
    response = test_client.post(
        "/v1/messages",
        json={
            "message_id": str(uuid4()),
            "conversation_id": conv_id,
            "from": "user1_id",
            "payload": {"type": "text", "text": "Hello"},
            "channels": ["whatsapp"]
        },
        headers={"Authorization": token}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
```

## Technology-Specific Decisions

### Python Dependencies (requirements.txt)

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
kafka-python==2.0.2
minio==7.2.0
bcrypt==4.1.1
pydantic==2.5.2
pydantic-settings==2.1.0
python-multipart==0.0.6
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.1
```

### Environment Configuration

**Decision**: Use pydantic-settings for environment-based configuration

```python
# core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://chat4all:password@localhost/chat4all"
    
    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    
    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "chat4all-files"
    
    # Security
    bcrypt_rounds: int = 12
    token_expiry_hours: int = 1
    
    class Config:
        env_file = ".env"

settings = Settings()
```

## Summary

All technical unknowns resolved. No "NEEDS CLARIFICATION" items remain. The implementation plan can proceed to Phase 1 (Design & Contracts) with confidence in:

1. FastAPI async patterns for non-blocking message acceptance
2. PostgreSQL schema with ENUM types and JSONB payloads
3. 3-topic Kafka architecture with intelligent routing
4. MinIO presigned URL pattern for direct client uploads
5. Simple token-based authentication (no JWT complexity)
6. Repository pattern for data access separation
7. Independent worker processes consuming from Kafka
8. pytest-based testing with fixtures for isolated test environments

All decisions align with Chat4All constitution principles and support the 4 user stories defined in the feature specification.
