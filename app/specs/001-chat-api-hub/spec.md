# Feature Specification: Chat4All API Hub

**Feature Branch**: `001-chat-api-hub`  
**Created**: 2025-11-24  
**Status**: Draft  
**Input**: User description: "Desenvolver a API para a plataforma Chat4All, uma prova de conceito acadêmica. A API deve funcionar como um hub de comunicação, permitindo o roteamento de mensagens e arquivos."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Simple Text Messaging (Priority: P1)

A user authenticates and sends a text message to another user in a private conversation. The message is routed through the system and delivered successfully.

**Why this priority**: This is the core functionality of any messaging platform. Without text messaging, the system delivers no value. This demonstrates the basic flow: authentication → conversation creation → message sending → asynchronous processing → delivery confirmation.

**Independent Test**: Can be fully tested by authenticating a user, creating a private conversation, sending a text message, and verifying the message status changes from "accepted" to "delivered" in the database.

**Acceptance Scenarios**:

1. **Given** two pre-registered users exist in the system, **When** User A authenticates and creates a private conversation with User B, **Then** a new conversation record is created with type "private" and both users as members.

2. **Given** an authenticated user has an active conversation, **When** the user posts a text message to `POST /v1/messages` with valid payload, **Then** the API returns HTTP 200 with `{"status": "accepted", "message_id": "<uuid>"}` within 500ms.

3. **Given** a message has been accepted by the API, **When** the background worker processes the message from Kafka, **Then** the message status is updated to "DELIVERED" in the database within 5 seconds.

4. **Given** an authenticated user in a conversation, **When** they retrieve messages via `GET /v1/conversations/{conversation_id}/messages`, **Then** all messages in the conversation are returned with correct timestamps, sender information, and delivery status.

---

### User Story 2 - Group Conversations (Priority: P2)

A user creates a group conversation with multiple members and sends messages that are visible to all group participants.

**Why this priority**: Group messaging extends the basic messaging capability to support team collaboration scenarios. This is a natural extension once 1:1 messaging works, and demonstrates the system can handle multiple recipients without requiring integration with external platforms.

**Independent Test**: Can be tested independently by authenticating a user, creating a group conversation with 3+ members, sending a message, and verifying all group members can retrieve the message from the conversation.

**Acceptance Scenarios**:

1. **Given** three or more pre-registered users exist, **When** User A creates a group conversation via `POST /v1/conversations` with all users in the members list, **Then** a conversation record with type "group" is created and all specified users become members.

2. **Given** a group conversation exists with multiple members, **When** any member sends a text message to the group, **Then** the message is stored with the conversation_id and is retrievable by all group members.

3. **Given** a group conversation with 5 members, **When** one member retrieves messages via `GET /v1/conversations/{conversation_id}/messages`, **Then** the response includes messages from all members with clear sender identification.

---

### User Story 3 - File Upload and Sharing (Priority: P3)

A user uploads a large file (up to 2GB) using chunked upload, then shares it in a conversation. Other users can retrieve the file reference.

**Why this priority**: File sharing is essential for modern communication but is more complex than text messaging. It can be implemented after core messaging works and demonstrates the system's ability to handle large binary data separate from message content.

**Independent Test**: Can be tested independently by authenticating a user, initiating a file upload, uploading chunks, completing the upload, sending a file message, and verifying the file reference appears in the conversation and is accessible via object storage.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they initiate a file upload via `POST /v1/files/initiate` with filename and size, **Then** the API returns a `file_id` and a presigned URL for the first chunk.

2. **Given** a file upload has been initiated, **When** the user uploads all chunks sequentially via `PATCH /v1/files/upload`, **Then** each chunk is stored in MinIO and the API confirms receipt.

3. **Given** all file chunks have been uploaded, **When** the user completes the upload via `POST /v1/files/complete` with the correct checksum, **Then** the file is marked as complete and available for messaging.

4. **Given** a completed file upload, **When** a user sends a message with `payload.type = "file"` and the file_id, **Then** the message is accepted and processed, and the file remains accessible through the conversation.

5. **Given** a file message exists in a conversation, **When** another conversation member retrieves messages, **Then** they receive the file_id and can construct a retrieval URL to access the file.

---

### User Story 4 - Multi-Channel Message Routing (Priority: P4)

A user sends a message and specifies delivery channels (WhatsApp, Instagram, or both). Mock connectors log the routing behavior to demonstrate the multi-channel architecture.

**Why this priority**: This demonstrates the distributed architecture and event-driven design but doesn't add functional value for end users in an academic POC. The mock connectors prove the concept without requiring real API integrations.

**Independent Test**: Can be tested by sending a message with specific channels array, then inspecting worker logs to confirm the correct mock connectors received and "processed" the message according to channel specifications.

**Acceptance Scenarios**:

1. **Given** an authenticated user with an active conversation, **When** they send a message with `"channels": ["whatsapp"]`, **Then** the message is published to the `whatsapp_outgoing` Kafka topic.

2. **Given** a message published to a channel-specific topic, **When** the WhatsApp mock connector worker processes it, **Then** the worker logs "INFO: Mensagem <uuid> enviada para o usuário <user_id> no WhatsApp" and updates message status.

3. **Given** a message sent with `"channels": ["all"]`, **When** processed by workers, **Then** the message is routed to all available mock connector topics (WhatsApp and Instagram).

4. **Given** a message sent with `"channels": ["whatsapp", "instagram"]`, **When** processed, **Then** both WhatsApp and Instagram mock connectors log the simulated delivery.

---

### Edge Cases

- **Invalid authentication**: What happens when a user provides incorrect credentials to `POST /auth/token`? System must return HTTP 401 with clear error message.

- **Missing conversation**: What happens when sending a message to a non-existent `conversation_id`? System must return HTTP 404 with error "Conversation not found".

- **Unauthorized conversation access**: What happens when a user tries to send a message to a conversation they are not a member of? System must return HTTP 403 with error "Access denied".

- **File upload interruption**: What happens when a user initiates a chunked upload but never completes it? System should have a cleanup mechanism to remove incomplete uploads after a timeout period (configurable, default 24 hours).

- **Duplicate message_id**: What happens when a client retries a message send with the same `message_id` (idempotency)? System must detect the duplicate and return the same response without creating a duplicate message.

- **Oversized file**: What happens when a user tries to upload a file larger than 2GB? System must reject the upload at initiation with HTTP 413 "Payload Too Large".

- **Invalid file_id in message**: What happens when sending a file message with a `file_id` that doesn't exist in MinIO? Worker should mark the message as FAILED and log the error.

- **Kafka unavailable**: What happens when the API cannot publish to Kafka? API should return HTTP 503 "Service Unavailable" with retry-after header.

- **Missing required fields**: What happens when message payload is missing required fields like `conversation_id` or `from`? API must return HTTP 400 with validation errors specifying which fields are missing.

- **Group member limit**: What happens when creating a group with too many members? System should enforce a maximum (recommended: 100 members) and return HTTP 400 if exceeded.

## Requirements *(mandatory)*

### Functional Requirements

**Authentication & Authorization**

- **FR-001**: System MUST provide a token-based authentication endpoint (`POST /auth/token`) that accepts username and password.
- **FR-002**: System MUST hash all user passwords using bcrypt before storing in the database.
- **FR-003**: Authentication tokens MUST be valid for at least 3600 seconds (1 hour).
- **FR-004**: All message and conversation endpoints MUST require valid authentication (token in request headers).
- **FR-005**: System MUST verify a user is a member of a conversation before allowing them to send messages or retrieve conversation data.

**Conversation Management**

- **FR-006**: System MUST allow creation of conversations with two types: "private" (exactly 2 members) and "group" (3 or more members).
- **FR-007**: Private conversations MUST enforce exactly 2 members in the members array.
- **FR-008**: Group conversations MUST support a minimum of 3 members and a maximum of 100 members.
- **FR-009**: System MUST persist conversation metadata including creation timestamp, conversation type, and member list.
- **FR-010**: System MUST provide an endpoint to list messages for a specific conversation (`GET /v1/conversations/{conversation_id}/messages`).
- **FR-011**: Message listing MUST include message content, sender identification, timestamps, and delivery status.

**Text Message Handling**

- **FR-012**: System MUST accept text messages via `POST /v1/messages` with a JSON payload containing message_id, conversation_id, from, to, channels, payload.type, payload.text, and priority fields.
- **FR-013**: System MUST validate that message_id is a valid UUID format.
- **FR-014**: System MUST implement idempotency for message sending using the client-provided message_id.
- **FR-015**: System MUST return HTTP 200 with `{"status": "accepted", "message_id": "<uuid>"}` within 500ms of accepting a message.
- **FR-016**: System MUST publish accepted messages to a Kafka topic for asynchronous processing.
- **FR-017**: System MUST NOT block API response waiting for message delivery confirmation.

**File Upload & Storage**

- **FR-018**: System MUST support resumable file uploads up to 2GB in size using a chunked upload protocol.
- **FR-019**: File upload initiation (`POST /v1/files/initiate`) MUST return a unique file_id and a presigned URL for uploading the first chunk.
- **FR-020**: System MUST accept file chunks via `PATCH /v1/files/upload` with file_id and chunk_id query parameters.
- **FR-021**: System MUST store file chunks in MinIO object storage.
- **FR-022**: File upload completion (`POST /v1/files/complete`) MUST verify file integrity using a checksum provided by the client.
- **FR-023**: System MUST mark files as "complete" only after successful checksum verification.
- **FR-024**: System MUST allow sending file messages with payload.type = "file" and a valid file_id.
- **FR-025**: System MUST reject file upload initiation requests exceeding 2GB with HTTP 413 error.

**Message Routing & Delivery**

- **FR-026**: System MUST have background workers that consume messages from Kafka topics.
- **FR-027**: Workers MUST process text messages and update their status to "DELIVERED" in the database.
- **FR-028**: Workers processing file messages MUST verify the file_id exists in MinIO before marking as delivered.
- **FR-029**: If a file_id is invalid or missing, workers MUST mark the message status as "FAILED" and log the error.
- **FR-030**: System MUST route messages to channel-specific Kafka topics based on the "channels" field in the message payload.
- **FR-031**: When channels = ["whatsapp"], system MUST publish to `whatsapp_outgoing` topic.
- **FR-032**: When channels = ["instagram"], system MUST publish to `instagram_outgoing` topic.
- **FR-033**: When channels = ["all"], system MUST publish to all available channel topics.

**Mock Connectors**

- **FR-034**: System MUST include mock connector workers for WhatsApp and Instagram that consume from channel-specific topics.
- **FR-035**: Mock connectors MUST NOT integrate with real external APIs.
- **FR-036**: Mock connectors MUST log simulated delivery events in the format: "INFO: Mensagem <uuid> enviada para o usuário <user_id> no <channel>".
- **FR-037**: Mock connectors MUST simulate successful delivery by updating message status after logging.

**Data Persistence**

- **FR-038**: System MUST store all conversation records in PostgreSQL.
- **FR-039**: System MUST store all message records with at minimum: message_id, conversation_id, sender, content, timestamp, status, and channel information.
- **FR-040**: System MUST store user records with username, hashed password, and user_id.
- **FR-041**: System MUST maintain message status history showing status transitions (e.g., ACCEPTED → DELIVERED).

**Error Handling**

- **FR-042**: System MUST return HTTP 401 for invalid authentication credentials.
- **FR-043**: System MUST return HTTP 403 when a user attempts to access a conversation they are not a member of.
- **FR-044**: System MUST return HTTP 404 when referencing a non-existent conversation or message.
- **FR-045**: System MUST return HTTP 400 with detailed validation errors when required fields are missing or invalid.
- **FR-046**: System MUST return HTTP 503 when dependent services (Kafka, MinIO) are unavailable.
- **FR-047**: All error responses MUST include a clear error message and error code.

### Key Entities

- **User**: Represents a system user with authentication credentials. Attributes include unique user_id, username (unique), hashed_password, and account metadata (creation date, status). Users are pre-seeded in the database for this phase.

- **Conversation**: Represents a communication context between users. Attributes include unique conversation_id, type (private or group), list of member user_ids, creation timestamp, and optional metadata. A conversation serves as a container for messages.

- **Message**: Represents a single communication unit within a conversation. Attributes include unique message_id (UUID), conversation_id (foreign key), sender user_id (from field), optional recipient user_id (to field for routing), payload (type and content - text or file_id), timestamp, delivery status (ACCEPTED, DELIVERED, FAILED), priority, and target channels array.

- **File**: Represents an uploaded file in object storage. Attributes include unique file_id, original filename, file size, content type, upload status (INITIATED, IN_PROGRESS, COMPLETED, FAILED), checksum for integrity verification, storage location reference (MinIO bucket and object key), upload initiation timestamp, and completion timestamp.

- **FileChunk**: Represents a portion of a file during chunked upload. Attributes include chunk_id, associated file_id, chunk sequence number, chunk size, storage location, and upload timestamp. This enables resumable uploads and tracking upload progress.

- **MessageStatus**: Tracks the status history of a message through its lifecycle. Attributes include status_id, message_id (foreign key), status value (ACCEPTED, IN_TRANSIT, DELIVERED, FAILED), timestamp of status change, and optional notes or error information. This provides audit trail for message delivery.

- **ConversationMember**: Junction entity representing the many-to-many relationship between users and conversations. Attributes include conversation_id, user_id, join timestamp, and membership status (active, left). This allows tracking who has access to which conversations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

**Performance & Responsiveness**

- **SC-001**: API endpoints respond to message submission requests within 500 milliseconds at the 95th percentile under normal load.
- **SC-002**: Background workers process and deliver text messages within 5 seconds of receipt from the message queue.
- **SC-003**: File upload initiation completes and returns references within 1 second.
- **SC-004**: The system maintains stable operation with 50 concurrent users sending messages simultaneously.

**Functional Completeness**

- **SC-005**: Users can successfully authenticate, create a conversation, send a text message, and verify delivery status in a single end-to-end test flow.
- **SC-006**: Users can upload a 100MB file using chunked upload, send it in a message, and verify the file reference appears in the conversation message list.
- **SC-007**: Group conversations with 10 members correctly deliver messages visible to all members.
- **SC-008**: All four user stories (text messaging, group conversations, file sharing, multi-channel routing) are independently demonstrable.

**Reliability & Data Integrity**

- **SC-009**: Message idempotency works correctly - sending the same message identifier twice results in only one message record and the same response.
- **SC-010**: File integrity verification catches corrupted uploads - completing upload with incorrect checksum results in rejection.
- **SC-011**: Zero message loss - 100% of accepted messages transition to either DELIVERED or FAILED status within 30 seconds.
- **SC-012**: Authentication tokens remain valid for their full declared lifetime without premature expiration.

**System Architecture Validation**

- **SC-013**: Message flow demonstrates asynchronous processing - API returns "accepted" immediately while delivery happens in background.
- **SC-014**: Mock connectors successfully log simulated deliveries for both WhatsApp and Instagram channels when specified.
- **SC-015**: Messages sent with multi-channel delivery appear in logs from all specified mock connectors.
- **SC-016**: Large file storage (files over 100MB) successfully stores without consuming API server memory.

**Documentation & Setup**

- **SC-017**: A developer unfamiliar with the project can follow setup documentation to configure the complete system and run all integration tests successfully within 30 minutes.
- **SC-018**: Auto-generated API documentation includes clear descriptions and example payloads for all endpoints.
- **SC-019**: All core endpoints (authentication, conversations, messages, files) appear in documentation with request/response schemas.

**Error Handling Quality**

- **SC-020**: Invalid authentication attempts return clear error messages with appropriate status codes.
- **SC-021**: Attempting to send messages to non-existent conversations returns proper error with specific message.
- **SC-022**: File uploads exceeding size limits are rejected immediately with clear explanation.

## Assumptions

This specification assumes the following constraints based on the academic POC context:

- **Pre-defined Architecture**: The implementation will use a REST API with asynchronous message processing, object storage for files, and relational database for structured data. These architectural decisions are predetermined by the academic project requirements.

- **Technology Stack**: The Chat4All constitution defines the specific technology stack (Python 3.11+, specific frameworks and databases). Implementation details and technology choices are documented in the constitution and will be elaborated in the technical plan phase.

- **User Management**: Users will be pre-seeded in the database. User registration and account management are out of scope for this phase.

- **Authentication Simplicity**: Token-based authentication uses a simplified approach without OAuth2 or JWT complexity, appropriate for academic demonstration.

- **Mock Integrations**: External platform connectors (WhatsApp, Instagram) are simulated rather than real integrations, sufficient to demonstrate the routing architecture.

- **Local Development**: The system is designed for local development and testing, not production cloud deployment.

- **API Contract Specifications**: Specific endpoint paths, payload structures, and HTTP methods are defined in the requirements to enable contract-first development and to align with the academic evaluation criteria.
