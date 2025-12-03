-- Chat4All Production-Ready Schema Migration
-- Migration: 003_production_ready.sql
-- Purpose: Add OAuth 2.0, Transactional Outbox, WebSocket, and File Upload enhancements
-- Date: 2025-11-30
-- Depends on: 001_initial_schema.sql, 002_seed_users.sql

-- ============================================================================
-- E1: OAuth 2.0 Authentication (Epic 0)
-- ============================================================================

-- Access Tokens Table
CREATE TABLE access_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,  -- SHA-256 hash of JWT token
    scope VARCHAR(255) DEFAULT 'read write',
    issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,  -- 15 minutes from issued_at
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT idx_access_token_hash UNIQUE (token_hash)
);

CREATE INDEX idx_access_token_user ON access_tokens(user_id, revoked, expires_at);
CREATE INDEX idx_access_token_expiration ON access_tokens(expires_at) WHERE revoked = FALSE;
CREATE INDEX idx_access_token_cleanup ON access_tokens(expires_at) WHERE revoked = FALSE AND expires_at < NOW();

COMMENT ON TABLE access_tokens IS 'OAuth 2.0 access tokens for API authentication (15min expiration)';
COMMENT ON COLUMN access_tokens.token_hash IS 'SHA-256 hash of JWT token for revocation checks';
COMMENT ON COLUMN access_tokens.scope IS 'OAuth 2.0 scopes: read, write, admin (space-separated)';

-- Refresh Tokens Table
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,  -- SHA-256 hash of opaque refresh token
    issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,  -- 30 days from issued_at
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP,
    last_used_at TIMESTAMP,  -- Updated on /auth/refresh
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT idx_refresh_token_hash UNIQUE (token_hash)
);

CREATE INDEX idx_refresh_token_user ON refresh_tokens(user_id, revoked, expires_at);
CREATE INDEX idx_refresh_token_cleanup ON refresh_tokens(expires_at) WHERE revoked = FALSE AND expires_at < NOW();

COMMENT ON TABLE refresh_tokens IS 'OAuth 2.0 refresh tokens for obtaining new access tokens (30 day expiration)';
COMMENT ON COLUMN refresh_tokens.last_used_at IS 'Timestamp of last successful /auth/refresh call';

-- ============================================================================
-- E2: Transactional Outbox Pattern (Epic 2 - Resilient Data Plane)
-- ============================================================================

-- Outbox Events Table
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(50) NOT NULL,  -- 'message', 'conversation', 'file', 'user'
    aggregate_id UUID NOT NULL,  -- Primary key of domain entity
    event_type VARCHAR(100) NOT NULL,  -- 'message.created', 'file.uploaded', etc.
    payload JSONB NOT NULL,  -- Complete event data for Kafka consumers
    published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    version INTEGER DEFAULT 1,  -- Retry counter for exponential backoff
    error_message TEXT,  -- Last error from Kafka publish failure
    
    CONSTRAINT idx_outbox_dedup UNIQUE (aggregate_id, event_type)
);

CREATE INDEX idx_outbox_unpublished ON outbox_events(published, created_at) WHERE published = FALSE;
CREATE INDEX idx_outbox_aggregate ON outbox_events(aggregate_type, aggregate_id, event_type);

COMMENT ON TABLE outbox_events IS 'Transactional Outbox for at-least-once Kafka event delivery';
COMMENT ON COLUMN outbox_events.version IS 'Retry counter: incremented on each failed publish (for exponential backoff)';
COMMENT ON COLUMN outbox_events.payload IS 'JSONB payload with full event data including trace_id, request_id';

-- ============================================================================
-- E3: WebSocket Connections (Epic 1 - Real-Time Communication)
-- ============================================================================

-- WebSocket Connections Table
CREATE TABLE websocket_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    connection_id VARCHAR(255) NOT NULL UNIQUE,  -- Unique connection identifier
    api_instance_id VARCHAR(255) NOT NULL,  -- API pod identifier for routing
    subscribed_conversations JSONB DEFAULT '[]',  -- Array of conversation IDs
    connected_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_ping_at TIMESTAMP NOT NULL DEFAULT NOW(),
    disconnected_at TIMESTAMP,
    
    CONSTRAINT check_disconnected_after_connected CHECK (disconnected_at IS NULL OR disconnected_at >= connected_at)
);

CREATE INDEX idx_websocket_user ON websocket_connections(user_id, disconnected_at) WHERE disconnected_at IS NULL;
CREATE INDEX idx_websocket_instance ON websocket_connections(api_instance_id, disconnected_at) WHERE disconnected_at IS NULL;
CREATE INDEX idx_websocket_stale ON websocket_connections(last_ping_at) WHERE disconnected_at IS NULL;

COMMENT ON TABLE websocket_connections IS 'Active WebSocket connections for real-time notifications';
COMMENT ON COLUMN websocket_connections.connection_id IS 'Unique connection ID for this WebSocket session';
COMMENT ON COLUMN websocket_connections.api_instance_id IS 'API pod identifier (e.g., api-pod-abc123) for routing';
COMMENT ON COLUMN websocket_connections.subscribed_conversations IS 'JSONB array of conversation IDs this connection is subscribed to';

-- ============================================================================
-- E4: File Upload Enhancements (Epic 4 - Full-Featured File Upload)
-- ============================================================================

-- Enhanced Files Table (replaces file_metadata with additional fields)
CREATE TABLE files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id VARCHAR(255) NOT NULL UNIQUE,  -- Client-provided upload session ID
    filename VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    checksum_sha256 VARCHAR(64),  -- SHA-256 hash for deduplication
    status file_status NOT NULL DEFAULT 'UPLOADING',
    minio_object_name VARCHAR(255),  -- Populated after merge
    uploaded_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total_chunks INTEGER NOT NULL,  -- Expected number of chunks
    uploaded_chunks INTEGER DEFAULT 0,  -- Chunks successfully uploaded
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    expires_at TIMESTAMP,  -- For garbage collection of incomplete uploads (24h)
    
    CONSTRAINT check_chunks_valid CHECK (uploaded_chunks >= 0 AND uploaded_chunks <= total_chunks),
    CONSTRAINT check_completed_chunks CHECK (status != 'COMPLETED' OR uploaded_chunks = total_chunks),
    CONSTRAINT check_completed_at CHECK (status != 'COMPLETED' OR completed_at IS NOT NULL)
);

CREATE INDEX idx_files_uploader ON files(uploaded_by);
CREATE INDEX idx_files_status ON files(status, created_at);
CREATE INDEX idx_files_gc ON files(status, expires_at) WHERE status = 'UPLOADING' AND expires_at < NOW();
CREATE INDEX idx_files_checksum ON files(checksum_sha256) WHERE checksum_sha256 IS NOT NULL;

COMMENT ON TABLE files IS 'Enhanced file upload metadata with chunking and resumability support';
COMMENT ON COLUMN files.upload_id IS 'Client-provided unique upload session ID for resuming uploads';
COMMENT ON COLUMN files.checksum_sha256 IS 'SHA-256 hash for deduplication (optional)';
COMMENT ON COLUMN files.expires_at IS 'Expiration for incomplete uploads (garbage collected after 24h)';

-- Enhanced File Chunks Table
CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    upload_id VARCHAR(255) NOT NULL REFERENCES files(upload_id) ON DELETE CASCADE,
    chunk_number INTEGER NOT NULL,
    size_bytes BIGINT NOT NULL,
    minio_object_name VARCHAR(255) NOT NULL,  -- Each chunk is a separate MinIO object
    checksum_sha256 VARCHAR(64),  -- Optional per-chunk checksum
    uploaded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    CONSTRAINT idx_chunk_dedup UNIQUE (upload_id, chunk_number)
);

CREATE INDEX idx_chunks_upload ON chunks(upload_id, chunk_number);

COMMENT ON TABLE chunks IS 'Individual file chunks for resumable uploads (5-10MB each)';
COMMENT ON COLUMN chunks.minio_object_name IS 'MinIO object name for this chunk (e.g., uploads/{upload_id}/chunk_{number})';

-- ============================================================================
-- Enhancements to Existing Tables
-- ============================================================================

-- Add UNIQUE constraint to messages.id for idempotency
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'idx_message_id_unique'
    ) THEN
        ALTER TABLE messages ADD CONSTRAINT idx_message_id_unique UNIQUE (id);
    END IF;
END $$;

COMMENT ON CONSTRAINT idx_message_id_unique ON messages IS 'Enforce idempotency: prevents duplicate messages with same UUID';

-- Add index for conversation_members.conversation_id + user_id (for WebSocket subscriptions)
CREATE INDEX IF NOT EXISTS idx_conversation_members_lookup ON conversation_members(conversation_id, user_id);

-- ============================================================================
-- Cleanup Functions (Optional - for background jobs)
-- ============================================================================

-- Function to cleanup expired tokens (run daily via cron)
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM access_tokens WHERE expires_at < NOW() AND revoked = FALSE;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    DELETE FROM refresh_tokens WHERE expires_at < NOW() AND revoked = FALSE;
    GET DIAGNOSTICS deleted_count = deleted_count + ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_tokens IS 'Cleanup expired access/refresh tokens (run daily via cron)';

-- Function to cleanup incomplete file uploads (run every 6 hours)
CREATE OR REPLACE FUNCTION cleanup_expired_uploads()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Delete chunks for expired uploads
    DELETE FROM chunks WHERE upload_id IN (
        SELECT upload_id FROM files 
        WHERE status = 'UPLOADING' AND expires_at < NOW()
    );
    
    -- Delete expired file records
    DELETE FROM files WHERE status = 'UPLOADING' AND expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_uploads IS 'Cleanup expired incomplete file uploads (run every 6 hours)';

-- Function to cleanup stale WebSocket connections (run every 5 minutes)
CREATE OR REPLACE FUNCTION cleanup_stale_connections()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    -- Mark connections as disconnected if no ping in 2 minutes
    UPDATE websocket_connections 
    SET disconnected_at = NOW()
    WHERE disconnected_at IS NULL 
      AND last_ping_at < NOW() - INTERVAL '2 minutes';
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_stale_connections IS 'Mark stale WebSocket connections as disconnected (run every 5 minutes)';

-- ============================================================================
-- E5: Conversation Management Views (Epic 5 - Enhanced API)
-- ============================================================================

-- Materialized View for Efficient Conversation Listing
CREATE MATERIALIZED VIEW conversation_view AS
SELECT 
    c.id AS conversation_id,
    cm.user_id,
    c.type AS conversation_type,
    c.name AS conversation_name,
    c.description,
    c.created_at AS conversation_created_at,
    m_last.id AS last_message_id,
    m_last.sender_id AS last_message_sender_id,
    u_sender.username AS last_message_sender_username,
    m_last.payload AS last_message_payload,
    m_last.created_at AS last_message_timestamp,
    COALESCE(unread.unread_count, 0) AS unread_count
FROM conversations c
INNER JOIN conversation_members cm ON c.id = cm.conversation_id
LEFT JOIN LATERAL (
    SELECT id, sender_id, payload, created_at
    FROM messages
    WHERE conversation_id = c.id
    ORDER BY created_at DESC
    LIMIT 1
) m_last ON TRUE
LEFT JOIN users u_sender ON m_last.sender_id = u_sender.id
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS unread_count
    FROM messages m
    WHERE m.conversation_id = c.id
      AND m.sender_id != cm.user_id
      AND m.status != 'READ'
) unread ON TRUE;

CREATE UNIQUE INDEX idx_conversation_view_pk ON conversation_view(conversation_id, user_id);
CREATE INDEX idx_conversation_view_user_timestamp ON conversation_view(user_id, last_message_timestamp DESC NULLS LAST);
CREATE INDEX idx_conversation_view_unread ON conversation_view(user_id, unread_count) WHERE unread_count > 0;

COMMENT ON MATERIALIZED VIEW conversation_view IS 'Optimized view for conversation listing with last message and unread count';
COMMENT ON COLUMN conversation_view.last_message_timestamp IS 'Timestamp of most recent message in conversation (NULL if no messages)';
COMMENT ON COLUMN conversation_view.unread_count IS 'Count of unread messages for this user in this conversation';

-- Function to refresh conversation view (run after message inserts/updates)
CREATE OR REPLACE FUNCTION refresh_conversation_view()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY conversation_view;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_conversation_view IS 'Refresh conversation_view materialized view (run after message activity)';

-- ============================================================================
-- Migration Complete
-- ============================================================================

-- Verify schema version
DO $$
BEGIN
    RAISE NOTICE 'Migration 003_production_ready.sql completed successfully';
    RAISE NOTICE 'New tables: access_tokens, refresh_tokens, outbox_events, websocket_connections, files, chunks';
    RAISE NOTICE 'Enhanced tables: messages (UNIQUE constraint), conversation_members (new index)';
END $$;
