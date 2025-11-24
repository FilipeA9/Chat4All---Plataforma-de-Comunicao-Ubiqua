# API Contracts: Chat4All API Hub

**Phase**: 1 - Design & Contracts  
**Created**: 2025-11-24  
**Purpose**: Define REST API endpoints, request/response schemas, and error responses

## Overview

This document specifies the REST API contract for Chat4All. All endpoints follow RESTful conventions with JSON request/response bodies. The API will auto-generate OpenAPI/Swagger documentation via FastAPI.

## Base URL

```
http://localhost:8000
```

## Authentication

Most endpoints require authentication via token in the `Authorization` header:

```http
Authorization: Bearer <token>
```

Endpoints requiring authentication are marked with 🔒.

---

## Endpoints

### 1. Authentication

#### POST /auth/token

Authenticate user and receive access token.

**Request**:
```json
{
  "username": "string",
  "password": "string"
}
```

**Response** (200 OK):
```json
{
  "access_token": "550e8400-e29b-41d4-a716-446655440000",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Error Responses**:
- `401 Unauthorized`: Invalid credentials
  ```json
  {
    "detail": "Invalid username or password"
  }
  ```

**Example**:
```bash
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "password123"}'
```

---

### 2. Conversations

#### POST /v1/conversations 🔒

Create a new conversation (private or group).

**Request**:
```json
{
  "type": "private | group",
  "members": ["uuid1", "uuid2", ...],
  "metadata": {
    "name": "Optional group name",
    "description": "Optional description"
  }
}
```

**Validation**:
- `type = "private"`: exactly 2 members required
- `type = "group"`: 3-100 members required
- All member user_ids must exist
- Authenticated user must be in members list

**Response** (201 Created):
```json
{
  "conversation_id": "uuid",
  "type": "private",
  "members": ["uuid1", "uuid2"],
  "created_at": "2025-11-24T10:30:00Z"
}
```

**Error Responses**:
- `400 Bad Request`: Invalid member count or members don't exist
  ```json
  {
    "detail": "Private conversations require exactly 2 members"
  }
  ```
- `401 Unauthorized`: Missing or invalid token
- `403 Forbidden`: Authenticated user not in members list

**Example**:
```bash
curl -X POST http://localhost:8000/v1/conversations \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "private",
    "members": ["user1-id", "user2-id"]
  }'
```

---

#### GET /v1/conversations/{conversation_id}/messages 🔒

Retrieve messages from a conversation.

**Path Parameters**:
- `conversation_id` (UUID): Conversation identifier

**Query Parameters**:
- `limit` (integer, optional, default=50): Maximum messages to return
- `offset` (integer, optional, default=0): Pagination offset

**Response** (200 OK):
```json
{
  "conversation_id": "uuid",
  "messages": [
    {
      "message_id": "uuid",
      "from": "uuid",
      "payload": {
        "type": "text",
        "text": "Hello, world!"
      },
      "status": "delivered",
      "created_at": "2025-11-24T10:31:00Z"
    },
    {
      "message_id": "uuid",
      "from": "uuid",
      "payload": {
        "type": "file",
        "file_id": "uuid",
        "filename": "document.pdf"
      },
      "status": "delivered",
      "created_at": "2025-11-24T10:32:00Z"
    }
  ],
  "total": 2,
  "limit": 50,
  "offset": 0
}
```

**Error Responses**:
- `401 Unauthorized`: Missing or invalid token
- `403 Forbidden`: User not a member of conversation
  ```json
  {
    "detail": "Access denied: not a conversation member"
  }
  ```
- `404 Not Found`: Conversation doesn't exist
  ```json
  {
    "detail": "Conversation not found"
  }
  ```

**Example**:
```bash
curl -X GET "http://localhost:8000/v1/conversations/<conversation_id>/messages?limit=20" \
  -H "Authorization: Bearer <token>"
```

---

### 3. Messages

#### POST /v1/messages 🔒

Send a message (text or file) to a conversation.

**Request**:
```json
{
  "message_id": "uuid",
  "conversation_id": "uuid",
  "from": "uuid",
  "to": "uuid",
  "channels": ["whatsapp", "instagram", "all"],
  "payload": {
    "type": "text | file",
    "text": "Message text (if type=text)",
    "file_id": "uuid (if type=file)"
  },
  "priority": "normal | high | low"
}
```

**Validation**:
- `message_id`: Must be valid UUID (client-generated for idempotency)
- `conversation_id`: Must exist
- `from`: Must match authenticated user
- `channels`: Array must not be empty; valid values: "whatsapp", "instagram", "all"
- `payload.type = "text"`: requires `payload.text`
- `payload.type = "file"`: requires `payload.file_id` (file must exist with status=completed)
- User must be member of conversation

**Response** (200 OK):
```json
{
  "status": "accepted",
  "message_id": "uuid"
}
```

**Idempotency**: If `message_id` already exists, returns same response without creating duplicate.

**Error Responses**:
- `400 Bad Request`: Validation errors
  ```json
  {
    "detail": "payload.text is required when type is 'text'"
  }
  ```
- `401 Unauthorized`: Missing or invalid token
- `403 Forbidden`: User not a member of conversation
- `404 Not Found`: Conversation or file not found
- `503 Service Unavailable`: Kafka unavailable
  ```json
  {
    "detail": "Message queue unavailable, please retry",
    "retry_after": 5
  }
  ```

**Example (Text Message)**:
```bash
curl -X POST http://localhost:8000/v1/messages \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "550e8400-e29b-41d4-a716-446655440000",
    "conversation_id": "<conversation_id>",
    "from": "<user_id>",
    "channels": ["whatsapp"],
    "payload": {
      "type": "text",
      "text": "Hello from Chat4All!"
    }
  }'
```

**Example (File Message)**:
```bash
curl -X POST http://localhost:8000/v1/messages \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "550e8400-e29b-41d4-a716-446655440001",
    "conversation_id": "<conversation_id>",
    "from": "<user_id>",
    "channels": ["all"],
    "payload": {
      "type": "file",
      "file_id": "<completed_file_id>"
    }
  }'
```

---

### 4. File Upload

#### POST /v1/files/initiate 🔒

Initiate chunked file upload.

**Request**:
```json
{
  "filename": "document.pdf",
  "file_size": 104857600,
  "content_type": "application/pdf"
}
```

**Validation**:
- `file_size`: Must be <= 2,147,483,648 (2GB)
- `filename`: Required

**Response** (201 Created):
```json
{
  "file_id": "uuid",
  "upload_url": "http://localhost:9000/chat4all-files/uuid/chunk_0?X-Amz-...",
  "chunk_size": 5242880,
  "expires_at": "2025-11-24T11:30:00Z"
}
```

**Fields**:
- `file_id`: Use this for subsequent upload operations and file messages
- `upload_url`: Presigned URL for uploading first chunk directly to MinIO
- `chunk_size`: Recommended chunk size (5MB)
- `expires_at`: URL expiration time (1 hour from initiation)

**Error Responses**:
- `400 Bad Request`: File size validation failed
  ```json
  {
    "detail": "File size exceeds 2GB limit"
  }
  ```
- `401 Unauthorized`: Missing or invalid token

**Example**:
```bash
curl -X POST http://localhost:8000/v1/files/initiate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "report.pdf",
    "file_size": 10485760,
    "content_type": "application/pdf"
  }'
```

---

#### PATCH /v1/files/upload 🔒

Upload a file chunk (or generate presigned URL for next chunk).

**Query Parameters**:
- `file_id` (UUID, required): File identifier from initiate
- `chunk_id` (integer, required): Chunk sequence number (0-indexed)

**Request Body**: 
- Binary chunk data (multipart/form-data)
- OR request for presigned URL (application/json with empty body)

**Response** (200 OK):
```json
{
  "file_id": "uuid",
  "chunk_id": 0,
  "status": "uploaded",
  "next_upload_url": "http://localhost:9000/chat4all-files/uuid/chunk_1?X-Amz-..."
}
```

**Error Responses**:
- `400 Bad Request`: Invalid chunk_id or file_id
- `404 Not Found`: File not found or not in uploading status
- `401 Unauthorized`: Missing or invalid token

**Example**:
```bash
# Upload chunk directly
curl -X PATCH "http://localhost:8000/v1/files/upload?file_id=<uuid>&chunk_id=0" \
  -H "Authorization: Bearer <token>" \
  -F "file=@chunk_0.bin"

# Or upload to presigned URL (bypasses API)
curl -X PUT "<presigned_url>" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@chunk_0.bin"
```

---

#### POST /v1/files/complete 🔒

Mark file upload as complete and verify integrity.

**Request**:
```json
{
  "file_id": "uuid",
  "checksum": "sha256_hash_of_complete_file"
}
```

**Validation**:
- `file_id`: Must exist with status="uploading"
- `checksum`: Must match calculated checksum of file in MinIO

**Response** (200 OK):
```json
{
  "file_id": "uuid",
  "status": "completed",
  "filename": "document.pdf",
  "file_size": 104857600
}
```

**Error Responses**:
- `400 Bad Request`: Checksum mismatch
  ```json
  {
    "detail": "Checksum validation failed: file may be corrupted"
  }
  ```
- `404 Not Found`: File not found
- `409 Conflict`: File already completed or failed
  ```json
  {
    "detail": "File upload already completed"
  }
  ```
- `401 Unauthorized`: Missing or invalid token

**Example**:
```bash
curl -X POST http://localhost:8000/v1/files/complete \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "<uuid>",
    "checksum": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  }'
```

---

## Error Response Format

All error responses follow this structure:

```json
{
  "detail": "Human-readable error message",
  "error_code": "OPTIONAL_ERROR_CODE",
  "field_errors": {
    "field_name": ["Validation error message"]
  }
}
```

**HTTP Status Codes**:
- `200 OK`: Successful request
- `201 Created`: Resource created
- `400 Bad Request`: Client error (validation, malformed request)
- `401 Unauthorized`: Missing or invalid authentication
- `403 Forbidden`: Authenticated but not authorized for resource
- `404 Not Found`: Resource doesn't exist
- `409 Conflict`: Resource conflict (e.g., duplicate message_id)
- `413 Payload Too Large`: File size exceeds limit
- `503 Service Unavailable`: Backend service (Kafka, MinIO) unavailable

---

## Rate Limiting

Not implemented for POC. In production, would implement:
- 100 requests/minute per user for message sending
- 10 file uploads/hour per user

---

## Versioning

API uses URL versioning (e.g., `/v1/messages`). Breaking changes would increment version (e.g., `/v2/messages`).

Current version: `v1`

---

## OpenAPI/Swagger Documentation

FastAPI automatically generates interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## Summary

**6 Endpoints**:
1. `POST /auth/token` - Authentication
2. `POST /v1/conversations` - Create conversation
3. `GET /v1/conversations/{id}/messages` - List messages
4. `POST /v1/messages` - Send message
5. `POST /v1/files/initiate` - Start file upload
6. `POST /v1/files/complete` - Finish file upload

**Key Features**:
- Token-based authentication
- Idempotent message sending (via client-provided message_id)
- Chunked file upload with presigned URLs
- Comprehensive error handling
- Auto-generated OpenAPI documentation

All contracts support the 4 user stories defined in spec.md and align with Chat4All constitution principles.
