# Data Model: Chat4All API Hub

**Phase**: 1 - Design & Contracts  
**Created**: 2025-11-24  
**Purpose**: Define database schema and entity relationships for the messaging system

## Overview

This document specifies the data model for Chat4All, designed to support text messaging, file sharing, and multi-channel routing. The model uses PostgreSQL with SQLAlchemy ORM, leveraging ENUM types for type safety and JSONB for flexible payload structures.

## Entity Relationship Diagram

```
┌─────────────┐         ┌──────────────────┐         ┌─────────────┐
│    User     │────────<│ConversationMember│>────────│Conversation │
└─────────────┘         └──────────────────┘         └─────────────┘
      │                                                       │
      │                                                       │
      │ (from_user_id)                                       │
      │                                                       │
      └───────────────────┐                                   │
                          │                                   │
                    ┌─────▼──────┐                           │
                    │  Message   │◄──────────────────────────┘
                    └─────┬──────┘         (conversation_id)
                          │
                          │ (message_id)
                          │
                    ┌─────▼──────────┐
                    │ MessageStatus  │
                    └────────────────┘
                    
    ┌──────────────┐
    │FileMetadata  │
    └──────────────┘
          │
          │ (file_id)
          │
    ┌─────▼──────┐
    │ FileChunk  │
    └────────────┘
    
    ┌──────────────┐
    │ AuthSession  │
    └──────────────┘
```

## Entities

### 1. User

Represents a registered user in the system. Users are pre-seeded for the POC phase.

**Fields**:
- `id` (UUID, PK): Unique user identifier
- `username` (VARCHAR(100), UNIQUE, NOT NULL): Login username
- `hashed_password` (VARCHAR(255), NOT NULL): bcrypt-hashed password
- `created_at` (TIMESTAMP, DEFAULT NOW()): Account creation timestamp
- `is_active` (BOOLEAN, DEFAULT TRUE): Account status

**Indexes**:
- PRIMARY KEY on `id`
- UNIQUE INDEX on `username`

**Constraints**:
- `username` must be unique
- `hashed_password` must be bcrypt hash (validated at application layer)

**SQLAlchemy Model**:
```python
class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    conversations = relationship("ConversationMember", back_populates="user")
    messages = relationship("Message", back_populates="sender")
    auth_sessions = relationship("AuthSession", back_populates="user")
```

### 2. Conversation

Represents a communication context (private 1:1 or group).

**Fields**:
- `id` (UUID, PK): Unique conversation identifier
- `type` (ENUM('private', 'group'), NOT NULL): Conversation type
- `created_at` (TIMESTAMP, DEFAULT NOW()): Creation timestamp
- `metadata` (JSONB, DEFAULT '{}'): Optional conversation metadata (name, description, etc.)

**Indexes**:
- PRIMARY KEY on `id`
- INDEX on `created_at` (for listing recent conversations)

**Constraints**:
- Private conversations enforced at application layer (exactly 2 members)
- Group conversations minimum 3 members enforced at application layer

**SQLAlchemy Model**:
```python
from enum import Enum as PyEnum

class ConversationType(str, PyEnum):
    PRIVATE = "private"
    GROUP = "group"

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    type = Column(Enum(ConversationType), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    metadata = Column(JSONB, default={})
    
    # Relationships
    members = relationship("ConversationMember", back_populates="conversation")
    messages = relationship("Message", back_populates="conversation")
```

### 3. ConversationMember

Junction table for many-to-many relationship between Users and Conversations.

**Fields**:
- `conversation_id` (UUID, FK → conversations.id, PK): Reference to conversation
- `user_id` (UUID, FK → users.id, PK): Reference to user
- `joined_at` (TIMESTAMP, DEFAULT NOW()): When user joined
- `is_active` (BOOLEAN, DEFAULT TRUE): Membership status (allows "leaving" groups)

**Indexes**:
- COMPOSITE PRIMARY KEY on `(conversation_id, user_id)`
- INDEX on `user_id` (for finding user's conversations)
- INDEX on `conversation_id` (for finding conversation members)

**Constraints**:
- CASCADE DELETE when conversation deleted
- CASCADE DELETE when user deleted

**SQLAlchemy Model**:
```python
class ConversationMember(Base):
    __tablename__ = "conversation_members"
    
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    joined_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="members")
    user = relationship("User", back_populates="conversations")
```

### 4. Message

Represents a single message (text or file) within a conversation.

**Fields**:
- `id` (UUID, PK): Client-provided message_id for idempotency
- `conversation_id` (UUID, FK → conversations.id, NOT NULL): Parent conversation
- `from_user_id` (UUID, FK → users.id, NOT NULL): Sender
- `to_user_id` (UUID, FK → users.id, NULLABLE): Optional recipient (for routing logic)
- `payload` (JSONB, NOT NULL): Message content
  - For text: `{"type": "text", "text": "message content"}`
  - For file: `{"type": "file", "file_id": "<uuid>"}`
- `channels` (ARRAY[VARCHAR], NOT NULL): Target delivery channels (e.g., `['whatsapp', 'instagram']`)
- `priority` (VARCHAR(20), DEFAULT 'normal'): Message priority
- `status` (ENUM('accepted', 'in_transit', 'delivered', 'failed'), DEFAULT 'accepted'): Current status
- `created_at` (TIMESTAMP, DEFAULT NOW()): Message creation time

**Indexes**:
- PRIMARY KEY on `id`
- INDEX on `conversation_id` (for retrieving conversation messages)
- INDEX on `(conversation_id, created_at)` (for ordered message retrieval)
- INDEX on `status` (for worker queries)

**Constraints**:
- `id` must be valid UUID (client-provided for idempotency)
- `payload` must contain `type` field
- CASCADE DELETE when conversation deleted

**SQLAlchemy Model**:
```python
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

class MessageStatus(str, PyEnum):
    ACCEPTED = "accepted"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True)  # Client-provided for idempotency
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    from_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    to_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    payload = Column(JSONB, nullable=False)
    channels = Column(ARRAY(String), nullable=False)
    priority = Column(String(20), default="normal")
    status = Column(Enum(MessageStatus), default=MessageStatus.ACCEPTED, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", foreign_keys=[from_user_id], back_populates="messages")
    status_history = relationship("MessageStatusHistory", back_populates="message")
```

### 5. MessageStatusHistory

Audit trail for message status transitions (constitutional requirement FR-041).

**Fields**:
- `id` (SERIAL, PK): Auto-increment ID
- `message_id` (UUID, FK → messages.id, NOT NULL): Reference to message
- `status` (ENUM('accepted', 'in_transit', 'delivered', 'failed'), NOT NULL): Status at this point
- `timestamp` (TIMESTAMP, DEFAULT NOW()): When status changed
- `notes` (TEXT, NULLABLE): Optional error messages or delivery information

**Indexes**:
- PRIMARY KEY on `id`
- INDEX on `message_id` (for retrieving message history)

**Constraints**:
- CASCADE DELETE when message deleted

**SQLAlchemy Model**:
```python
class MessageStatusHistory(Base):
    __tablename__ = "message_status_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(Enum(MessageStatus), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)
    
    # Relationships
    message = relationship("Message", back_populates="status_history")
```

### 6. FileMetadata

Metadata for uploaded files stored in MinIO.

**Fields**:
- `id` (UUID, PK): Unique file identifier (used as file_id in messages)
- `uploader_id` (UUID, FK → users.id, NOT NULL): User who uploaded
- `filename` (VARCHAR(255), NOT NULL): Original filename
- `file_size` (BIGINT, NOT NULL): File size in bytes (max 2GB = 2,147,483,648)
- `content_type` (VARCHAR(100), NULLABLE): MIME type
- `checksum` (VARCHAR(64), NULLABLE): SHA-256 checksum for integrity
- `storage_path` (VARCHAR(500), NOT NULL): MinIO object key (e.g., `<file_id>/complete`)
- `status` (ENUM('uploading', 'completed', 'failed'), DEFAULT 'uploading'): Upload status
- `created_at` (TIMESTAMP, DEFAULT NOW()): Upload initiation time
- `completed_at` (TIMESTAMP, NULLABLE): Upload completion time

**Indexes**:
- PRIMARY KEY on `id`
- INDEX on `uploader_id`
- INDEX on `status` (for cleanup jobs)

**Constraints**:
- `file_size` must be <= 2,147,483,648 (2GB)
- `status` = 'completed' requires `checksum` and `completed_at`

**SQLAlchemy Model**:
```python
class FileStatus(str, PyEnum):
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"

class FileMetadata(Base):
    __tablename__ = "file_metadata"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    uploader_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    content_type = Column(String(100), nullable=True)
    checksum = Column(String(64), nullable=True)
    storage_path = Column(String(500), nullable=False)
    status = Column(Enum(FileStatus), default=FileStatus.UPLOADING, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    uploader = relationship("User")
    chunks = relationship("FileChunk", back_populates="file_metadata")
```

### 7. FileChunk

Tracks individual chunks during multipart upload.

**Fields**:
- `id` (SERIAL, PK): Auto-increment ID
- `file_id` (UUID, FK → file_metadata.id, NOT NULL): Parent file
- `chunk_number` (INTEGER, NOT NULL): Sequence number (0-indexed)
- `chunk_size` (INTEGER, NOT NULL): Size of this chunk in bytes
- `storage_path` (VARCHAR(500), NOT NULL): MinIO object key for chunk
- `uploaded_at` (TIMESTAMP, DEFAULT NOW()): When chunk completed

**Indexes**:
- PRIMARY KEY on `id`
- UNIQUE INDEX on `(file_id, chunk_number)` (prevents duplicate chunks)
- INDEX on `file_id`

**Constraints**:
- CASCADE DELETE when file_metadata deleted

**SQLAlchemy Model**:
```python
class FileChunk(Base):
    __tablename__ = "file_chunks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(UUID(as_uuid=True), ForeignKey("file_metadata.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_number = Column(Integer, nullable=False)
    chunk_size = Column(Integer, nullable=False)
    storage_path = Column(String(500), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    file_metadata = relationship("FileMetadata", back_populates="chunks")
    
    __table_args__ = (
        UniqueConstraint('file_id', 'chunk_number', name='uq_file_chunk'),
    )
```

### 8. AuthSession

Simple token-based authentication sessions.

**Fields**:
- `id` (SERIAL, PK): Auto-increment ID
- `user_id` (UUID, FK → users.id, NOT NULL): User owning this session
- `token` (VARCHAR(255), UNIQUE, NOT NULL): Authentication token (UUID)
- `created_at` (TIMESTAMP, DEFAULT NOW()): Session creation time
- `expires_at` (TIMESTAMP, NOT NULL): Session expiration time (created_at + 1 hour)

**Indexes**:
- PRIMARY KEY on `id`
- UNIQUE INDEX on `token` (for fast lookups)
- INDEX on `user_id`
- INDEX on `expires_at` (for cleanup jobs)

**Constraints**:
- CASCADE DELETE when user deleted
- `expires_at` must be > `created_at`

**SQLAlchemy Model**:
```python
class AuthSession(Base):
    __tablename__ = "auth_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    
    # Relationships
    user = relationship("User", back_populates="auth_sessions")
```

## Validation Rules

### Application-Level Validations

**Conversation**:
- Private conversations: `COUNT(members) == 2`
- Group conversations: `COUNT(members) >= 3 AND COUNT(members) <= 100`

**Message**:
- `payload.type` must be 'text' or 'file'
- If `payload.type == 'text'`: must have `payload.text` field
- If `payload.type == 'file'`: must have `payload.file_id` field, and file must exist with status='completed'
- `channels` array must not be empty
- `id` must be valid UUID v4

**FileMetadata**:
- `file_size` must be <= 2,147,483,648 bytes (2GB)
- `checksum` required when `status == 'completed'`

**AuthSession**:
- `expires_at` must be >= NOW() for session to be valid
- Token must be unique across all active sessions

## Migration Strategy

**Initial Migration** (`001_initial_schema.py`):
1. Create ENUM types
2. Create tables in dependency order:
   - users
   - auth_sessions
   - conversations
   - conversation_members
   - messages
   - message_status_history
   - file_metadata
   - file_chunks

**Seed Data** (`002_seed_users.py`):
- Create 5 test users for development/testing
- Passwords: bcrypt hashed "password123"

## Database Queries Patterns

**Common Queries**:

```sql
-- Get conversation messages (ordered)
SELECT * FROM messages 
WHERE conversation_id = $1 
ORDER BY created_at ASC;

-- Check user is conversation member
SELECT 1 FROM conversation_members 
WHERE conversation_id = $1 AND user_id = $2 AND is_active = TRUE;

-- Get messages pending delivery (for workers)
SELECT * FROM messages 
WHERE status = 'accepted' 
LIMIT 100;

-- Authenticate user
SELECT u.* FROM users u
JOIN auth_sessions s ON s.user_id = u.id
WHERE s.token = $1 AND s.expires_at > NOW();

-- Get file metadata by message
SELECT f.* FROM file_metadata f
JOIN messages m ON m.payload->>'file_id' = f.id::text
WHERE m.id = $1;
```

## Performance Considerations

1. **Indexes**: All foreign keys indexed for join performance
2. **JSONB**: `payload` field uses GIN index if querying by type frequently
3. **Partitioning**: Not needed for POC scale (<10k messages expected)
4. **Connection Pooling**: SQLAlchemy pool_size=5, max_overflow=10 for local dev

## Summary

Data model supports all 4 user stories with:
- 8 core entities
- Clear relationships and referential integrity
- ENUM types for type safety
- JSONB for flexible message payloads
- Audit trail via MessageStatusHistory
- Idempotency via client-provided message IDs
- Simple authentication without JWT complexity

All design decisions align with Chat4All constitution and support the functional requirements from spec.md.
