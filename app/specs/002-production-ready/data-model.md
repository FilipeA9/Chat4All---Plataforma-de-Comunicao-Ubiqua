# Data Model: Production-Ready Platform Evolution

**Feature**: Production-Ready Platform Evolution  
**Branch**: `002-production-ready`  
**Date**: 2025-11-30

## Overview

This document defines the data models required for production-ready features including OAuth 2.0 authentication (access and refresh tokens), Transactional Outbox pattern (outbox events), file upload chunking (file chunks), and WebSocket connection tracking. All models are designed for PostgreSQL 15+ with high availability (Patroni clusters) and include indexes for performance.

---

## E1: OAuth 2.0 Tokens

### Entity: `access_tokens`

**Purpose**: Store issued access tokens for revocation checks and audit logging.

**Schema**:

```sql
CREATE TABLE access_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,  -- SHA-256 hash of JWT token (for revocation)
    scope VARCHAR(255) DEFAULT 'read write',
    issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Indexes
    CONSTRAINT idx_access_token_hash UNIQUE (token_hash),
    INDEX idx_access_token_user (user_id, revoked, expires_at),
    INDEX idx_access_token_expiration (expires_at) WHERE revoked = FALSE
);

-- Cleanup expired tokens (run daily via cron job)
CREATE INDEX idx_access_token_cleanup ON access_tokens(expires_at) 
WHERE revoked = FALSE AND expires_at < NOW();
```

**Fields**:
- `id`: Primary key, unique identifier for the token record
- `user_id`: Foreign key to `users.id`, identifies the token owner
- `token_hash`: SHA-256 hash of the JWT token (hashed for security, allows revocation without storing plaintext JWT)
- `scope`: OAuth 2.0 scopes granted to the token (e.g., 'read', 'write', 'admin')
- `issued_at`: Timestamp when the token was issued
- `expires_at`: Timestamp when the token expires (15 minutes from issued_at for access tokens)
- `revoked`: Boolean flag indicating if the token has been manually revoked (logout)
- `revoked_at`: Timestamp when the token was revoked
- `created_at`: Record creation timestamp (for audit logging)

**Validation Rules**:
- `expires_at` MUST be 15 minutes after `issued_at` for access tokens
- `token_hash` MUST be unique (prevents token replay if hash collision occurs)
- `scope` MUST match the regex `^[a-z\s]+$` (space-separated lowercase words)
- `revoked_at` MUST be NULL if `revoked` is FALSE

**State Transitions**:
1. **Active**: `revoked = FALSE`, `expires_at > NOW()`
2. **Expired**: `revoked = FALSE`, `expires_at <= NOW()` (natural expiration)
3. **Revoked**: `revoked = TRUE` (manual revocation via POST /auth/revoke)

**Relationships**:
- `user_id` → `users.id` (many-to-one: one user can have multiple active access tokens)

---

### Entity: `refresh_tokens`

**Purpose**: Store long-lived refresh tokens (30 days) for obtaining new access tokens without re-authentication.

**Schema**:

```sql
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,  -- SHA-256 hash of refresh token
    issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,     -- 30 days from issued_at
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP,
    last_used_at TIMESTAMP,           -- Updated on each /auth/refresh call
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Indexes
    CONSTRAINT idx_refresh_token_hash UNIQUE (token_hash),
    INDEX idx_refresh_token_user (user_id, revoked, expires_at),
    INDEX idx_refresh_token_cleanup ON refresh_tokens(expires_at) 
    WHERE revoked = FALSE AND expires_at < NOW()
);
```

**Fields**:
- `id`: Primary key
- `user_id`: Foreign key to `users.id`
- `token_hash`: SHA-256 hash of the refresh token (opaque string, not a JWT)
- `issued_at`: Timestamp when the refresh token was issued
- `expires_at`: Timestamp when the refresh token expires (30 days from issued_at)
- `revoked`: Boolean flag for manual revocation (logout, security incident)
- `revoked_at`: Timestamp of revocation
- `last_used_at`: Timestamp of the last successful /auth/refresh call (for usage tracking)
- `created_at`: Record creation timestamp

**Validation Rules**:
- `expires_at` MUST be 30 days after `issued_at`
- `token_hash` MUST be unique
- `last_used_at` MUST be <= NOW() and >= issued_at
- `revoked_at` MUST be NULL if `revoked` is FALSE

**State Transitions**:
1. **Active**: `revoked = FALSE`, `expires_at > NOW()`
2. **Expired**: `revoked = FALSE`, `expires_at <= NOW()`
3. **Revoked**: `revoked = TRUE`

**Relationships**:
- `user_id` → `users.id` (many-to-one: one user can have multiple refresh tokens across devices)

**Security Notes**:
- Refresh tokens MUST be stored as SHA-256 hashes, never plaintext
- Each /auth/refresh call SHOULD update `last_used_at` for usage analytics
- Implement token rotation: POST /auth/refresh SHOULD invalidate the old refresh token and issue a new one (optional enhancement)

---

## E2: Transactional Outbox

### Entity: `outbox_events`

**Purpose**: Implement the Transactional Outbox pattern to guarantee at-least-once message delivery. All state-changing operations (message creation, status updates) write to this table in the same transaction as the domain entity.

**Schema**:

```sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(50) NOT NULL,  -- e.g., 'message', 'conversation', 'file'
    aggregate_id UUID NOT NULL,           -- e.g., message.id, conversation.id
    event_type VARCHAR(100) NOT NULL,     -- e.g., 'message.created', 'message.delivered'
    payload JSONB NOT NULL,               -- Full event data (includes all fields needed by consumers)
    published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    version INTEGER DEFAULT 1,            -- Incremented on each retry for exponential backoff
    error_message TEXT,                   -- Last error message if publish failed
    
    -- Indexes
    INDEX idx_outbox_unpublished (published, created_at) WHERE published = FALSE,
    INDEX idx_outbox_aggregate (aggregate_type, aggregate_id, event_type),
    CONSTRAINT idx_outbox_dedup UNIQUE (aggregate_id, event_type)  -- Prevents duplicate events
);

-- Partitioning for high-volume scenarios (optional, recommended for >10M events/day)
-- CREATE TABLE outbox_events (...)
-- PARTITION BY RANGE (created_at);
-- CREATE TABLE outbox_events_2025_11 PARTITION OF outbox_events FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
```

**Fields**:
- `id`: Primary key for the outbox entry
- `aggregate_type`: Type of domain entity (e.g., 'message', 'conversation', 'file')
- `aggregate_id`: Primary key of the domain entity (e.g., message.id)
- `event_type`: Semantic event name (e.g., 'message.created', 'file.uploaded')
- `payload`: JSONB containing the complete event data (serialized domain entity + metadata)
- `published`: Boolean flag indicating if the event has been successfully published to Kafka
- `published_at`: Timestamp of successful Kafka publish
- `created_at`: Timestamp when the event was written to the outbox
- `version`: Retry counter, incremented on each failed publish attempt (used for exponential backoff)
- `error_message`: Last error message from Kafka publish failure (for debugging)

**Validation Rules**:
- `aggregate_type` MUST match one of: 'message', 'conversation', 'file', 'user'
- `event_type` MUST match the pattern `^[a-z_]+\.[a-z_]+$` (e.g., 'message.created')
- `payload` MUST be valid JSONB
- `published_at` MUST be NULL if `published` is FALSE
- `version` MUST be >= 1

**State Transitions**:
1. **Pending**: `published = FALSE`, `version = 1` (initial state after INSERT)
2. **Retrying**: `published = FALSE`, `version > 1`, `error_message` populated (after failed publish)
3. **Published**: `published = TRUE`, `published_at` populated (final state after successful Kafka publish)

**Relationships**:
- `aggregate_id` → Domain entity primary key (soft foreign key, not enforced by database due to polymorphism)

**Payload Example** (message.created event):

```json
{
  "message_id": "123e4567-e89b-12d3-a456-426614174000",
  "conversation_id": "223e4567-e89b-12d3-a456-426614174000",
  "sender_id": "323e4567-e89b-12d3-a456-426614174000",
  "content": "Hello, world!",
  "channels": ["whatsapp"],
  "created_at": "2025-11-30T12:00:00Z",
  "metadata": {
    "trace_id": "abc123",
    "request_id": "req-456"
  }
}
```

**Poller Logic**: The outbox poller worker queries `SELECT * FROM outbox_events WHERE published = FALSE ORDER BY created_at LIMIT 100 FOR UPDATE SKIP LOCKED`, publishes each event to Kafka, and updates `published = TRUE` on success.

---

## E3: File Upload (Chunked)

### Entity: `file_uploads` (Enhanced)

**Purpose**: Track file upload sessions for resumable chunked uploads (up to 2GB). Enhanced version of the existing `files` table with chunk metadata.

**Schema**:

```sql
-- Existing files table (from 001-chat-api-hub)
-- Enhanced with chunk metadata
CREATE TABLE files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    uploader_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_size BIGINT NOT NULL,           -- Total file size in bytes (max 2GB = 2147483648)
    mime_type VARCHAR(100) NOT NULL,
    checksum_sha256 VARCHAR(64),         -- SHA-256 checksum for integrity verification
    storage_key VARCHAR(500) NOT NULL,   -- MinIO/S3 object key (e.g., "files/conv123/abc.jpg")
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending', 'uploading', 'completed', 'failed'
    
    -- Chunked upload metadata (NEW)
    chunk_size INTEGER,                  -- Chunk size in bytes (e.g., 5MB = 5242880)
    total_chunks INTEGER,                -- Total number of chunks (file_size / chunk_size, rounded up)
    uploaded_chunks INTEGER DEFAULT 0,   -- Count of successfully uploaded chunks
    
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,              -- Timestamp when all chunks were merged
    
    -- Indexes
    INDEX idx_file_conversation (conversation_id, status),
    INDEX idx_file_uploader (uploader_id, status),
    INDEX idx_file_status_created (status, created_at),
    CHECK (file_size <= 2147483648),     -- Enforce 2GB max
    CHECK (status IN ('pending', 'uploading', 'completed', 'failed'))
);

-- Trigger to update updated_at timestamp
CREATE TRIGGER update_file_updated_at
BEFORE UPDATE ON files
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
```

**Fields**:
- `id`: Primary key, also used as `upload_id` in API responses
- `conversation_id`: Foreign key to `conversations.id`
- `uploader_id`: Foreign key to `users.id` (user initiating the upload)
- `filename`: Original filename (e.g., "vacation_video.mp4")
- `file_size`: Total file size in bytes (max 2GB)
- `mime_type`: MIME type (e.g., "video/mp4", "image/jpeg")
- `checksum_sha256`: SHA-256 checksum of the complete file (for integrity verification after merge)
- `storage_key`: MinIO/S3 object key where the complete file will be stored
- `status`: Upload status ('pending' → 'uploading' → 'completed' or 'failed')
- `chunk_size`: Size of each chunk in bytes (recommended 5-10MB)
- `total_chunks`: Total number of chunks (calculated as `ceil(file_size / chunk_size)`)
- `uploaded_chunks`: Count of successfully uploaded chunks (updated after each chunk upload)
- `created_at`: Upload session creation timestamp
- `updated_at`: Last update timestamp
- `completed_at`: Timestamp when all chunks were merged into the final file

**Validation Rules**:
- `file_size` MUST be <= 2GB (enforced by CHECK constraint)
- `chunk_size` MUST be between 1MB and 50MB (validated in API logic)
- `total_chunks` MUST equal `ceil(file_size / chunk_size)`
- `uploaded_chunks` MUST be <= total_chunks
- `checksum_sha256` MUST be 64 hexadecimal characters (SHA-256 hash)
- `completed_at` MUST be NULL if status != 'completed'

**State Transitions**:
1. **Pending**: `status = 'pending'`, `uploaded_chunks = 0` (POST /v1/files/initiate)
2. **Uploading**: `status = 'uploading'`, `0 < uploaded_chunks < total_chunks` (POST /v1/files/{upload_id}/chunks)
3. **Completed**: `status = 'completed'`, `uploaded_chunks = total_chunks`, `completed_at` populated (POST /v1/files/{upload_id}/complete)
4. **Failed**: `status = 'failed'` (validation failure, merge failure, or timeout)

**Relationships**:
- `conversation_id` → `conversations.id` (many-to-one: one conversation can have many files)
- `uploader_id` → `users.id` (many-to-one: one user can upload many files)

---

### Entity: `file_chunks`

**Purpose**: Track individual file chunks for resumable uploads. Each chunk is stored temporarily in MinIO until all chunks are received and merged.

**Schema**:

```sql
CREATE TABLE file_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    chunk_number INTEGER NOT NULL,       -- 1-based chunk index (1, 2, 3, ..., total_chunks)
    chunk_size INTEGER NOT NULL,         -- Actual size of this chunk in bytes
    storage_key VARCHAR(500) NOT NULL,   -- MinIO/S3 key for this chunk (e.g., "chunks/file123/chunk-001")
    checksum_sha256 VARCHAR(64),         -- SHA-256 checksum for this chunk (optional integrity check)
    uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Indexes
    CONSTRAINT idx_file_chunk_unique UNIQUE (file_id, chunk_number),
    INDEX idx_file_chunk_file (file_id, chunk_number)
);
```

**Fields**:
- `id`: Primary key for the chunk record
- `file_id`: Foreign key to `files.id` (parent upload session)
- `chunk_number`: 1-based chunk index (e.g., chunk 1, chunk 2, ..., chunk N)
- `chunk_size`: Actual size of this chunk in bytes (may be smaller for the last chunk)
- `storage_key`: MinIO/S3 object key where this chunk is stored
- `checksum_sha256`: SHA-256 checksum of this chunk (optional, for paranoid validation)
- `uploaded_at`: Timestamp when the chunk was successfully uploaded

**Validation Rules**:
- `chunk_number` MUST be between 1 and `files.total_chunks`
- `chunk_size` MUST be <= `files.chunk_size` (last chunk may be smaller)
- `storage_key` MUST be unique across all chunks
- `checksum_sha256` MUST be 64 hexadecimal characters if provided

**Relationships**:
- `file_id` → `files.id` (many-to-one: one file upload has many chunks)

**Lifecycle**:
1. **Creation**: POST /v1/files/{upload_id}/chunks creates a `file_chunks` record and uploads the chunk to MinIO
2. **Validation**: API verifies chunk_number is not a duplicate (UNIQUE constraint)
3. **Merge**: POST /v1/files/{upload_id}/complete triggers a merge worker that reads all chunks in order, concatenates them, and writes the final file to MinIO
4. **Cleanup**: After successful merge, all `file_chunks` records and their MinIO objects are deleted (garbage collection)

---

## E4: WebSocket Connections (Logical)

### Entity: `websocket_connections` (In-Memory Only)

**Purpose**: Track active WebSocket connections for real-time message delivery. This is an **in-memory data structure** (not stored in PostgreSQL) maintained by the API instances.

**Structure** (Python):

```python
from dataclasses import dataclass
from typing import Set
from fastapi import WebSocket

@dataclass
class WebSocketConnection:
    user_id: str                      # User ID of the connected client
    websocket: WebSocket              # FastAPI WebSocket object
    conversation_ids: Set[str]        # Set of conversation IDs the user is subscribed to
    connected_at: datetime            # Timestamp when the connection was established
    last_ping_at: datetime            # Timestamp of the last heartbeat/ping

# In-memory storage (per API instance)
class WebSocketManager:
    def __init__(self):
        # Map user_id -> set of WebSocket connections (one user can have multiple connections)
        self.user_connections: dict[str, set[WebSocketConnection]] = defaultdict(set)
        
        # Map conversation_id -> set of WebSocket connections (for efficient broadcast)
        self.conversation_connections: dict[str, set[WebSocketConnection]] = defaultdict(set)
    
    async def connect(self, user_id: str, websocket: WebSocket):
        """Register a new WebSocket connection."""
        await websocket.accept()
        
        # Fetch user's conversations from database
        user_conversations = await get_user_conversations(user_id)
        
        connection = WebSocketConnection(
            user_id=user_id,
            websocket=websocket,
            conversation_ids=set(user_conversations),
            connected_at=datetime.utcnow(),
            last_ping_at=datetime.utcnow()
        )
        
        # Add to user_connections
        self.user_connections[user_id].add(connection)
        
        # Add to conversation_connections
        for conv_id in connection.conversation_ids:
            self.conversation_connections[conv_id].add(connection)
    
    async def disconnect(self, user_id: str, websocket: WebSocket):
        """Unregister a WebSocket connection."""
        # Find and remove the connection
        for conn in self.user_connections[user_id]:
            if conn.websocket == websocket:
                # Remove from conversation_connections
                for conv_id in conn.conversation_ids:
                    self.conversation_connections[conv_id].discard(conn)
                
                # Remove from user_connections
                self.user_connections[user_id].discard(conn)
                break
    
    async def broadcast_to_conversation(self, conversation_id: str, event: dict):
        """Send an event to all clients subscribed to a conversation."""
        for conn in self.conversation_connections.get(conversation_id, set()):
            try:
                await conn.websocket.send_json(event)
            except Exception as e:
                # Connection broken, remove it
                await self.disconnect(conn.user_id, conn.websocket)
```

**Fields** (logical):
- `user_id`: User ID of the connected client
- `websocket`: FastAPI WebSocket connection object
- `conversation_ids`: Set of conversation IDs the user is a member of (preloaded on connection)
- `connected_at`: Timestamp when the connection was established
- `last_ping_at`: Timestamp of the last heartbeat (updated every 30 seconds)

**Validation Rules**:
- A user can have multiple concurrent WebSocket connections (e.g., mobile + desktop)
- Each connection MUST authenticate via JWT token in the connection URL
- Connections MUST be removed after 60 seconds of inactivity (no heartbeat)

**State Transitions**:
1. **Connected**: WebSocket accepted, user_id authenticated, subscribed to conversations
2. **Active**: Receiving events, responding to pings
3. **Disconnected**: Connection closed (client disconnect, network failure, timeout)

**Relationships**:
- `user_id` → `users.id` (logical, not enforced)
- `conversation_ids` → `conversations.id` (logical, not enforced)

**Redis Pub/Sub Integration**: When a message is created on Instance A, it publishes to Redis channel `conversation:{conversation_id}:events`. All API instances (A, B, C) subscribe to this channel and forward the event to their locally connected WebSocket clients in that conversation.

---

## Summary

All new entities are designed for production-grade requirements:

| Entity | Purpose | Key Features |
|--------|---------|--------------|
| `access_tokens` | OAuth 2.0 access token tracking | 15-minute expiration, revocation support, SHA-256 hashed |
| `refresh_tokens` | OAuth 2.0 refresh token tracking | 30-day expiration, last_used_at tracking, token rotation ready |
| `outbox_events` | Transactional Outbox for at-least-once delivery | JSONB payload, idempotency via UNIQUE constraint, retry versioning |
| `files` (enhanced) | File upload session tracking | Chunked upload metadata, resumable uploads, 2GB max |
| `file_chunks` | Individual file chunk tracking | 1-based chunk_number, temporary storage keys, merge-ready |
| `websocket_connections` | In-memory WebSocket connection tracking | Conversation subscriptions, Redis Pub/Sub integration, heartbeat monitoring |

All database schema changes are **backward compatible** with the existing 001-chat-api-hub data model (users, conversations, messages). The enhanced `files` table adds new columns without modifying existing columns, allowing gradual migration.
