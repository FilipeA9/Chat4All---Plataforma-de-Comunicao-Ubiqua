-- Chat4All API Hub - Initial Schema Migration
-- Creates all required tables for the application
-- Run this script to initialize a new database

-- Create ENUM types
CREATE TYPE conversation_type AS ENUM ('PRIVATE', 'GROUP');
CREATE TYPE message_status AS ENUM ('ACCEPTED', 'PROCESSING', 'DELIVERED', 'FAILED');
CREATE TYPE file_status AS ENUM ('UPLOADING', 'COMPLETED', 'FAILED');

-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);

-- Conversations table
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    type conversation_type NOT NULL,
    name VARCHAR(100),
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_conversations_type ON conversations(type);
CREATE INDEX idx_conversations_created_at ON conversations(created_at);

-- Conversation members table (junction table)
CREATE TABLE conversation_members (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(conversation_id, user_id)
);

CREATE INDEX idx_conversation_members_conversation ON conversation_members(conversation_id);
CREATE INDEX idx_conversation_members_user ON conversation_members(user_id);

-- Messages table
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    status message_status NOT NULL DEFAULT 'ACCEPTED',
    channels TEXT[] NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_sender ON messages(sender_id);
CREATE INDEX idx_messages_status ON messages(status);
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);
CREATE INDEX idx_messages_payload_type ON messages((payload->>'type'));

-- Message status history table
CREATE TABLE message_status_history (
    id SERIAL PRIMARY KEY,
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    status message_status NOT NULL,
    channel VARCHAR(50),
    details JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_message_status_history_message ON message_status_history(message_id);
CREATE INDEX idx_message_status_history_status ON message_status_history(status);
CREATE INDEX idx_message_status_history_created_at ON message_status_history(created_at DESC);

-- File metadata table
CREATE TABLE file_metadata (
    id UUID PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    minio_object_name VARCHAR(500) NOT NULL,
    uploaded_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status file_status NOT NULL DEFAULT 'uploading',
    checksum VARCHAR(64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_file_metadata_uploader ON file_metadata(uploaded_by);
CREATE INDEX idx_file_metadata_status ON file_metadata(status);
CREATE INDEX idx_file_metadata_created_at ON file_metadata(created_at DESC);

-- File chunks table (for chunked upload tracking)
CREATE TABLE file_chunks (
    id SERIAL PRIMARY KEY,
    file_id UUID NOT NULL REFERENCES file_metadata(id) ON DELETE CASCADE,
    chunk_number INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_id, chunk_number)
);

CREATE INDEX idx_file_chunks_file ON file_chunks(file_id);

-- Auth sessions table
CREATE TABLE auth_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token UUID UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL
);

CREATE INDEX idx_auth_sessions_token ON auth_sessions(token);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX idx_auth_sessions_expires_at ON auth_sessions(expires_at);

-- Comments
COMMENT ON TABLE users IS 'Application users with authentication credentials';
COMMENT ON TABLE conversations IS 'Private (2 members) or group (3-100 members) conversations';
COMMENT ON TABLE conversation_members IS 'Junction table linking users to conversations';
COMMENT ON TABLE messages IS 'Messages sent in conversations (text or file)';
COMMENT ON TABLE message_status_history IS 'Audit trail of message status changes';
COMMENT ON TABLE file_metadata IS 'Metadata for uploaded files (max 2GB)';
COMMENT ON TABLE file_chunks IS 'Chunked upload tracking for large files';
COMMENT ON TABLE auth_sessions IS 'Active authentication sessions with expiry';

-- Initial schema complete
-- Next step: Run 002_seed_users.sql to create test users
