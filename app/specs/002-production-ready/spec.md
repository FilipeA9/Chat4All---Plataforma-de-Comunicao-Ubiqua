# Feature Specification: Production-Ready Platform Evolution

**Feature Branch**: `002-production-ready`  
**Created**: 2025-11-30  
**Status**: Draft  
**Input**: User description: "Evolve Chat4All v2 prototype into production-ready, scalable, and resilient communication platform with real-time communication, resilient data plane, fault-tolerant infrastructure, full-featured file upload, enhanced API functionality, and production-grade observability"

## Clarifications

### Session 2025-11-30

- Q: What is the strategic priority for the gRPC implementation? Should it be a complete 1:1 mirror of the REST API, or prioritized for specific use cases? → A: gRPC for internal service-to-service communication only. Keep REST as the primary external API for this phase. Provides performance benefits for high-volume internal communication without the complexity of maintaining two complete external APIs.

- Q: What are the detailed requirements for the new authentication system? Should we implement OAuth2 flows, integrate with third-party IdPs? → A: Implement OAuth 2.0 Client Credentials flow with JWT tokens. Provides constitution-mandated OAuth 2.0 compliance, supports WebSocket authentication, rate limiting (user identification), and audit logging without the complexity of full user registration flows (deferred).

- Q: How should the system handle authentication with external messaging platforms (WhatsApp, Instagram, Telegram)? Official APIs or third-party libraries? → A: Use mock connectors with simulated external API behavior for this production-ready phase. Real external platform integration requires business agreements, API approval processes, and platform-specific compliance. Mock connectors allow validation of complete architecture without external dependencies.

- Q: Does the platform require multi-tenancy where different customers use the platform with isolated data? What level of data isolation? → A: Single-tenant architecture. Each customer organization gets their own isolated deployment (Kubernetes namespace with dedicated resources). Provides complete data isolation, simpler security model, easier compliance, and independent scaling per customer. Focus on horizontal scalability within a single tenant to handle millions of end-users.

- Q: What is the expected scope for message search functionality? Simple text search within conversations or global full-text search? → A: Defer message search to future phase (not in production-ready). Focus on core infrastructure (real-time delivery, resilience, observability). When added later, PostgreSQL's full-text search can provide conversation-scoped search without requiring Elasticsearch. Global cross-conversation search deferred until actual user demand justifies complexity.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Real-Time Message Notifications (Priority: P1)

As a user actively viewing a conversation, I want to receive new messages instantly without refreshing the page, so that my conversation feels fluid and natural like a real chat application.

**Why this priority**: Real-time communication is the core differentiator between a modern messaging platform and a basic API. Without it, the user experience is broken and polling creates unnecessary load. This is the foundation for a production-ready messaging system.

**Independent Test**: Can be fully tested by opening two browser windows with different authenticated users in the same conversation. When User A sends a message, User B should see it appear instantly without any manual action. Delivers immediate value as a standalone real-time messaging experience.

**Acceptance Scenarios**:

1. **Given** User A and User B are both connected to a conversation via WebSocket, **When** User A sends a message, **Then** User B receives the message in real-time within 100ms
2. **Given** a user is connected via WebSocket, **When** another user marks messages as READ, **Then** the first user receives the status update notification instantly
3. **Given** a user has a flaky network connection, **When** the WebSocket disconnects and reconnects, **Then** the user successfully re-establishes the connection without losing messages
4. **Given** the system has 5,000 concurrent WebSocket connections, **When** a high-volume conversation receives 100 messages per second, **Then** all connected users receive notifications without degradation

---

### User Story 2 - Resilient Message Processing (Priority: P1)

As a developer sending messages through the API, I want a guarantee that when I receive a 202 Accepted response, the message will be delivered even if downstream systems experience temporary failures, so I can trust the platform's reliability.

**Why this priority**: Data integrity and reliability are non-negotiable for a production system. Without transactional guarantees, messages can be lost silently, destroying user trust. This is critical infrastructure that must be in place before scaling.

**Independent Test**: Can be fully tested by shutting down Kafka broker mid-transaction, verifying the message is still persisted in the outbox table, then restarting Kafka and confirming the message is eventually published and processed. Delivers measurable reliability improvement.

**Acceptance Scenarios**:

1. **Given** the API accepts a message submission, **When** Kafka is unavailable at the moment of event publishing, **Then** the message is persisted in the outbox and published to Kafka when it becomes available
2. **Given** a message is published to Kafka multiple times due to retries, **When** the worker processes it, **Then** the message is written to the database exactly once (idempotent processing)
3. **Given** a message processing worker fails after 3 retry attempts, **When** the final attempt fails, **Then** the message is moved to the Dead Letter Queue and an alert is triggered
4. **Given** multiple messages in the same conversation are submitted concurrently, **When** they are processed by workers, **Then** they appear in the conversation in the exact order they were sent
5. **Given** a duplicate message ID is submitted, **When** the system attempts to insert it, **Then** the database constraint prevents duplication and returns an appropriate response

---

### User Story 3 - Zero-Downtime Infrastructure (Priority: P2)

As an SRE managing the platform, I want the system to survive the failure of any single component without causing service disruption or data loss, so I can perform maintenance and handle failures confidently.

**Why this priority**: High availability is essential for production readiness and directly supports the 99.95% SLA requirement. While not user-facing functionality, it's critical infrastructure that enables reliable service delivery. Prioritized after basic functionality but before advanced features.

**Independent Test**: Can be fully tested by running a load test with active traffic, then systematically killing individual components (API pod, database primary, Kafka broker) and verifying the system continues processing messages with automatic failover. Delivers measurable uptime improvement.

**Acceptance Scenarios**:

1. **Given** a PostgreSQL primary node fails, **When** automatic failover occurs, **Then** a replica is promoted to primary within 30 seconds and the API continues accepting requests
2. **Given** one Kafka broker in a 3-broker cluster fails, **When** producers attempt to publish messages, **Then** messages are successfully written to remaining in-sync replicas without data loss
3. **Given** 3 API instances are running behind a load balancer, **When** one instance crashes, **Then** traffic is automatically routed to healthy instances without user-visible errors
4. **Given** CPU usage exceeds 80% on API pods, **When** the HorizontalPodAutoscaler detects high load, **Then** additional API pods are automatically provisioned within 60 seconds
5. **Given** a Kafka consumer experiences a transient failure, **When** it rejoins the consumer group, **Then** it resumes processing from the last committed offset without message loss or duplication

---

### User Story 4 - Resumable Large File Uploads (Priority: P2)

As a user on a mobile device with an unreliable connection, I want to upload a large video file (up to 2GB) and be able to resume the upload if it gets interrupted, without starting over from the beginning.

**Why this priority**: File sharing is a core messaging platform feature, and large files are common (videos, documents). Resumable uploads dramatically improve user experience on mobile networks. This is important but can be implemented after core messaging reliability is established.

**Independent Test**: Can be fully tested by initiating a large file upload, simulating a network interruption mid-upload, then resuming from the last successful chunk and verifying the complete file is correctly assembled. Delivers standalone value for file-sharing use cases.

**Acceptance Scenarios**:

1. **Given** a user initiates a 1GB file upload, **When** the connection drops after uploading 500MB, **Then** the user can resume the upload starting from chunk 501 without re-uploading the first 500MB
2. **Given** a file is uploaded in 20 chunks, **When** all chunks are successfully uploaded, **Then** a background worker merges the chunks into a single file in MinIO within 5 seconds
3. **Given** a user starts uploading a file but abandons it halfway, **When** 24 hours pass, **Then** a garbage collection job automatically deletes the incomplete chunks from both database and MinIO
4. **Given** a user uploads 15 chunks out of 20, **When** they query the upload status, **Then** they receive accurate progress information (75% complete, chunks 1-15 received)
5. **Given** two users upload files with the same SHA-256 checksum, **When** the second upload completes, **Then** the system uses deduplication to avoid storing the file twice (optional optimization)

---

### User Story 5 - Conversation Discovery and Management (Priority: P3)

As a user opening the application, I want to see a list of all my conversations sorted by recent activity, and be able to mark conversations as read, so I can efficiently manage my communications.

**Why this priority**: This is essential for usability but can be implemented after core messaging infrastructure is solid. Users can manually track conversations in the short term. Prioritized lower because the API already supports creating and retrieving individual conversations.

**Independent Test**: Can be fully tested by creating multiple conversations with different timestamps, querying the list endpoint, and verifying conversations are returned in correct order with proper pagination. Marking a conversation as read should trigger real-time notifications to other participants.

**Acceptance Scenarios**:

1. **Given** a user is a member of 50 conversations, **When** they request GET /v1/conversations, **Then** they receive a paginated list sorted by the timestamp of the most recent message (newest first)
2. **Given** a user opens a conversation with 10 unread messages, **When** they call POST /v1/conversations/{id}/read, **Then** all messages are marked as READ and other conversation members receive real-time status updates
3. **Given** a user requests their conversation list, **When** the query executes, **Then** it completes in under 100ms even with 1000 conversations by using optimized joins (no N+1 queries)
4. **Given** a user sends 100 API requests in 1 minute, **When** they attempt a 101st request, **Then** they receive a 429 Too Many Requests response with a Retry-After header

---

### User Story 6 - Full Observability for Operations (Priority: P3)

As an SRE investigating a user complaint about delayed messages, I want to see real-time dashboards showing latency at each component and trace the path of a specific message, so I can quickly identify bottlenecks.

**Why this priority**: Observability is critical for production operations but doesn't directly impact end-user functionality. It's essential for debugging and optimization but can be added after core features are working. Prioritized last because manual debugging is possible in early stages.

**Independent Test**: Can be fully tested by generating synthetic load, viewing Grafana dashboards to confirm metrics are being collected, searching for a specific message by trace ID in Jaeger, and verifying all service hops appear in the distributed trace. Delivers operational visibility.

**Acceptance Scenarios**:

1. **Given** all services are running, **When** an SRE accesses Prometheus, **Then** they can query metrics for request rates, error rates, latency percentiles, and Kafka consumer lag for all services
2. **Given** a message is submitted through the API, **When** the SRE searches for its trace ID in Jaeger, **Then** they see the complete trace including API ingestion, Kafka publish, worker processing, and database writes with timing for each span
3. **Given** a service generates an error log, **When** the SRE searches Kibana/Loki, **Then** they can filter logs by trace ID, service name, and severity level to find the error in context
4. **Given** pre-configured Grafana dashboards, **When** the SRE opens the "Message Pipeline Health" dashboard, **Then** they see real-time visualizations of API latency, Kafka lag, worker throughput, and database connection pool utilization
5. **Given** Kafka consumer lag exceeds 10,000 messages, **When** the alert threshold is breached, **Then** an alert is triggered in the monitoring system (e.g., Alertmanager)

---

### Edge Cases

- What happens when a WebSocket client disconnects during message transmission? System must buffer the message and deliver it when the client reconnects.
- What happens when a chunk upload fails but the client doesn't retry? After 24 hours, the garbage collection job cleans up the orphaned chunks.
- What happens when database replication lag causes a read-after-write inconsistency? The API should read from the primary for critical operations or implement eventual consistency warnings.
- What happens when the outbox poller crashes mid-processing? The transactional semantics ensure no messages are lost; the poller resumes from the last processed outbox entry on restart.
- What happens when a user attempts to upload a malicious file disguised with a valid extension? The system must validate file content (magic bytes) in addition to extension and checksum.
- What happens when Redis Pub/Sub is temporarily unavailable? WebSocket notifications may be delayed, but messages are still persisted and can be retrieved via polling as a fallback.
- What happens when the DLQ fills up with failed messages? The system must trigger critical alerts and potentially pause message ingestion to prevent cascading failures.
- What happens when a user has 10,000 concurrent WebSocket connections from compromised devices? Rate limiting and connection limits per user must prevent resource exhaustion.

## Requirements *(mandatory)*

### Functional Requirements

#### Epic 0: Authentication and Authorization (Foundation)

- **FR-AUTH-01**: System MUST implement OAuth 2.0 Client Credentials flow for API authentication
- **FR-AUTH-02**: System MUST issue JWT tokens with 15-minute expiration and refresh tokens for extended sessions
- **FR-AUTH-03**: JWT tokens MUST include claims: user_id, tenant_id (single-tenant, always same value), issued_at, expires_at, and scope
- **FR-AUTH-04**: System MUST provide POST /auth/token endpoint accepting client_id and client_secret, returning access_token and refresh_token
- **FR-AUTH-05**: System MUST provide POST /auth/refresh endpoint accepting a refresh_token and returning a new access_token
- **FR-AUTH-06**: All protected API endpoints MUST validate JWT signature and expiration before processing requests
- **FR-AUTH-07**: System MUST return 401 Unauthorized for invalid or expired tokens with WWW-Authenticate header indicating Bearer scheme
- **FR-AUTH-08**: WebSocket connections MUST authenticate by passing the JWT token in the connection URL (/ws?token={jwt})
- **FR-AUTH-09**: System MUST store refresh tokens in PostgreSQL with user association, issued_at, expires_at (30 days), and revoked status
- **FR-AUTH-10**: System MUST provide POST /auth/revoke endpoint to invalidate refresh tokens (logout functionality)

#### Epic 1: Real-Time Communication Layer

- **FR-RT-01**: System MUST provide a WebSocket endpoint at /ws for clients to establish persistent, bidirectional connections
- **FR-RT-02**: System MUST authenticate users via the JWT token provided in the WebSocket connection query parameter before accepting the connection
- **FR-RT-03**: System MUST push new messages, message status updates (DELIVERED, READ), and conversation events to connected clients in real-time via WebSocket
- **FR-RT-04**: System MUST handle at least 10,000 concurrent WebSocket connections per API instance without degradation
- **FR-RT-05**: System MUST use Redis Pub/Sub to fan out notifications across multiple API instances to ensure messages reach the correct connected client regardless of which instance they're connected to
- **FR-RT-06**: System MUST implement a connection manager to track active WebSocket clients and their subscribed conversations
- **FR-RT-07**: System MUST send periodic heartbeat/ping messages to detect stale connections and clean them up

#### Epic 2: Resilient and Consistent Data Plane

- **FR-DP-01**: System MUST implement the Transactional Outbox pattern to ensure atomicity between database writes and Kafka event publishing
- **FR-DP-02**: System MUST create an outbox_events table where each message write is accompanied by an outbox entry in a single database transaction
- **FR-DP-03**: System MUST run a separate outbox poller worker that reads from outbox_events and reliably publishes events to Kafka, marking entries as published
- **FR-DP-04**: Message processing workers MUST be idempotent, using database constraints (UNIQUE on message.id) and INSERT ... ON CONFLICT DO NOTHING to prevent duplicate processing
- **FR-DP-05**: Workers MUST implement exponential backoff retry logic (initial delay 1s, max 3 retries) for transient failures
- **FR-DP-06**: Messages that fail processing after 3 retries MUST be published to a Dead Letter Queue (message_processing_dlq Kafka topic)
- **FR-DP-07**: System MUST trigger alerts when messages are sent to the DLQ for manual investigation
- **FR-DP-08**: Kafka producers MUST use conversation_id as the partition key to ensure message ordering within conversations
- **FR-DP-09**: The messages table MUST have a UNIQUE constraint on the id (UUID) column to enforce idempotency at the database level
- **FR-DP-10**: System MUST prevent race conditions by using database-level locking or optimistic concurrency control for state updates

#### Epic 3: Scalable and Fault-Tolerant Infrastructure

- **FR-HA-01**: PostgreSQL MUST be deployed in a high-availability cluster with 1 primary and at least 2 replicas
- **FR-HA-02**: PostgreSQL MUST support automatic failover with promotion of a replica to primary within 30 seconds of primary failure
- **FR-HA-03**: Kafka MUST be deployed as a cluster with at least 3 brokers
- **FR-HA-04**: All Kafka topics MUST be configured with replication.factor=3 and min.insync.replicas=2
- **FR-HA-05**: API and worker services MUST be deployed with at least 3 replicas in a Kubernetes cluster
- **FR-HA-06**: API services MUST be fronted by a load balancer (Kubernetes Ingress) that distributes traffic and performs health checks
- **FR-HA-07**: Kubernetes HorizontalPodAutoscaler MUST be configured to automatically scale API and worker pods based on CPU/memory usage (target 70% utilization)
- **FR-HA-08**: All Docker Compose container_name fields MUST be removed to allow scaling with docker-compose up --scale
- **FR-HA-09**: System MUST monitor and alert on single points of failure or under-replicated partitions

#### Epic 4: Full-Featured File Upload

- **FR-FU-01**: System MUST support resumable uploads by allowing clients to upload files in smaller, sequential chunks (recommended chunk size: 5-10MB)
- **FR-FU-02**: POST /v1/files/initiate endpoint MUST return an upload_id, expected chunk count, and chunk size
- **FR-FU-03**: System MUST provide a new endpoint PATCH /v1/files/upload/{upload_id}/{chunk_number} to upload individual file chunks
- **FR-FU-04**: POST /v1/files/complete endpoint MUST validate that all chunks have been uploaded before triggering the merge process
- **FR-FU-05**: System MUST trigger an asynchronous worker (via Kafka event) to merge uploaded chunks into a single file in MinIO
- **FR-FU-06**: The merge worker MUST use MinIO's server-side compose/multipart upload API to efficiently merge chunks
- **FR-FU-07**: After successful merge, the worker MUST delete individual chunk objects from MinIO to free storage
- **FR-FU-08**: System MUST maintain a file_uploads table with status tracking (UPLOADING, MERGING, COMPLETED, FAILED)
- **FR-FU-09**: System MUST provide a GET /v1/files/upload/{upload_id}/status endpoint to query upload progress (chunks received, percentage complete)
- **FR-FU-10**: System MUST implement a daily cron job to delete abandoned uploads (UPLOADING status > 24 hours old) from both database and MinIO

#### Epic 5: Enhanced API Functionality

- **FR-API-01**: System MUST implement GET /v1/conversations endpoint that returns a paginated list of conversations the authenticated user is a member of
- **FR-API-02**: GET /v1/conversations MUST sort results by the timestamp of the last message in each conversation (most recent first)
- **FR-API-03**: GET /v1/conversations MUST optimize the query to avoid N+1 problems by using joins to fetch last message data in a single query
- **FR-API-04**: GET /v1/conversations MUST support pagination parameters (limit, offset) with a default limit of 50 and maximum of 100
- **FR-API-05**: System MUST implement POST /v1/conversations/{id}/read endpoint to mark all messages in a conversation as READ for the authenticated user
- **FR-API-06**: POST /v1/conversations/{id}/read MUST trigger real-time notifications to other conversation members via WebSocket
- **FR-API-07**: All state-changing API endpoints (POST, PATCH, DELETE) MUST be protected by rate limiting (60 requests per minute per user)
- **FR-API-08**: Rate limiting MUST be distributed across API instances using Redis as the backing store
- **FR-API-09**: When rate limit is exceeded, the API MUST return 429 Too Many Requests with a Retry-After header

#### Epic 6: Production-Grade Observability

- **FR-OBS-01**: All services (API, workers) MUST expose Prometheus metrics at a /metrics endpoint
- **FR-OBS-02**: Metrics MUST include request rates, error rates, latency histograms (p50, p95, p99), Kafka consumer lag, and resource usage
- **FR-OBS-03**: System MUST implement distributed tracing using OpenTelemetry
- **FR-OBS-04**: A unique trace ID MUST be generated at the API gateway for each request and propagated through Kafka headers and downstream services
- **FR-OBS-05**: All services MUST be instrumented with OpenTelemetry spans for key operations (HTTP requests, Kafka publish/consume, database queries)
- **FR-OBS-06**: System MUST be configured to export traces to Jaeger or Zipkin
- **FR-OBS-07**: All logs MUST be structured JSON with mandatory fields: timestamp, level, service, trace_id, request_id, message
- **FR-OBS-08**: Logs MUST be centralized in ELK stack (Elasticsearch, Logstash, Kibana) or Loki+Grafana
- **FR-OBS-09**: System MUST include pre-configured Grafana dashboards for key metrics: API health, message pipeline throughput, Kafka lag, database performance
- **FR-OBS-10**: Alerting rules MUST be configured in Prometheus Alertmanager for critical conditions: API error rate > 5%, Kafka consumer lag > 10,000 messages, database connection pool exhaustion

### Non-Functional Requirements (Constitution-Driven)

**Reliability** (Principle II):
- **NFR-001**: System MUST guarantee at-least-once message delivery even if Kafka is temporarily unavailable (via Transactional Outbox)
- **NFR-002**: System MUST maintain ≥99.95% availability (SLA) with no single points of failure
- **NFR-003**: All operations MUST be idempotent to handle retries safely
- **NFR-004**: System MUST implement circuit breakers to prevent cascading failures
- **NFR-005**: Data replication factor MUST be ≥3 for PostgreSQL and Kafka

**Performance** (Principle III):
- **NFR-006**: API latency MUST be <200ms p99 from request receipt to Kafka publish
- **NFR-007**: WebSocket notification delivery MUST be <100ms from event occurrence to client receipt
- **NFR-008**: System MUST support processing 10M messages/minute at peak load
- **NFR-009**: Database queries MUST complete <50ms p95 with proper indexing
- **NFR-010**: File chunk uploads MUST complete <5s for 10MB chunks on typical broadband connections

**Scalability** (Principle III):
- **NFR-011**: All API and worker services MUST be horizontally scalable (stateless design)
- **NFR-012**: System MUST support scaling to millions of concurrent WebSocket connections across multiple API instances
- **NFR-013**: Kafka topics MUST be partitioned (100+ partitions) to enable parallel processing
- **NFR-014**: Kubernetes HPA MUST automatically scale pods based on resource utilization

**Consistency** (Principle IV):
- **NFR-015**: Messages within a conversation MUST be processed in send order (Kafka partition key = conversation_id)
- **NFR-016**: System MUST provide strong eventual consistency with deduplication windows ≥24 hours
- **NFR-017**: Read-after-write consistency MUST be guaranteed for message submission (read from primary or use version tokens)

**Security** (Principle VI):
- **NFR-018**: All external communication MUST use TLS 1.3+ (API endpoints, WebSocket)
- **NFR-019**: WebSocket connections MUST be authenticated via token validation before accepting
- **NFR-020**: Rate limiting MUST prevent abuse (60 req/min per user for state-changing operations)
- **NFR-021**: File uploads MUST validate content type (magic bytes) in addition to declared MIME type
- **NFR-022**: Audit logging MUST capture all security events (authentication failures, rate limit violations, DLQ additions)

**Observability** (Principle VII):
- **NFR-023**: All services MUST expose Prometheus metrics with standardized naming (service_operation_duration_seconds, etc.)
- **NFR-024**: Distributed tracing MUST have <1% sampling at minimum to keep overhead acceptable
- **NFR-025**: Centralized logging MUST support querying by trace_id, service, level, and time range
- **NFR-026**: Dashboards MUST refresh every 30 seconds to provide near-real-time visibility
- **NFR-027**: Critical alerts MUST be delivered via multiple channels (Slack, PagerDuty, email)

### Key Entities

- **OutboxEvent**: Represents a pending event that needs to be published to Kafka. Contains event_id (UUID), aggregate_id (e.g., message_id), event_type (MessageCreated, MessageRead), payload (JSON), status (PENDING, PUBLISHED), created_at, published_at. Used to implement Transactional Outbox pattern.

- **FileUpload**: Represents a multi-chunk file upload in progress. Contains upload_id (UUID), user_id, original_filename, total_size_bytes, total_chunks, chunks_received (JSON array of chunk numbers), status (UPLOADING, MERGING, COMPLETED, FAILED), created_at, completed_at. Enables resumable uploads.

- **WebSocketConnection**: Logical representation of an active WebSocket client connection. Contains connection_id (UUID), user_id, connected_at, last_heartbeat_at, subscribed_conversations (array). Used by connection manager to route notifications.

- **ConversationView**: Denormalized view of conversations with last message metadata for efficient listing. Contains conversation_id, user_id, last_message_timestamp, last_message_content (preview), unread_count. Updated via triggers or materialized views.

- **DeadLetterMessage**: Represents a message that failed processing after all retries. Contains dlq_id (UUID), original_message_id, original_topic, failure_reason, retry_count, payload (original message), created_at. Used for manual investigation and potential replay.

## Success Criteria *(mandatory)*

### Measurable Outcomes

**User Experience**:
- **SC-001**: Users receive new messages in real-time with <100ms latency when both parties are connected via WebSocket
- **SC-002**: Users can upload files up to 2GB with the ability to resume from any interruption point without data loss
- **SC-003**: Users can view their conversation list sorted by recent activity in <100ms even with 1000 conversations

**Reliability**:
- **SC-004**: System achieves ≥99.95% uptime over a 30-day measurement period (max 21.6 minutes downtime/month)
- **SC-005**: Zero messages are lost when the system experiences single component failures (database, Kafka, API pod)
- **SC-006**: 100% of messages submitted to the API are either successfully delivered or moved to DLQ with alerts (no silent failures)

**Scalability**:
- **SC-007**: System successfully processes 10M messages/minute during peak load testing without degradation
- **SC-008**: System maintains 10,000 concurrent WebSocket connections per API instance with <5% CPU overhead
- **SC-009**: Kubernetes HPA automatically scales API pods from 3 to 10 replicas when CPU utilization exceeds 70%, completing scale-up within 60 seconds

**Performance**:
- **SC-010**: API p99 latency remains <200ms from request ingestion to Kafka publish confirmation under normal load
- **SC-011**: Database queries execute <50ms p95 latency with proper indexing on conversation listing endpoint
- **SC-012**: WebSocket notifications are delivered to clients within 100ms of the triggering event (message sent, status changed)

**Operational Excellence**:
- **SC-013**: SREs can trace any message through the entire system (API → Kafka → Worker → Database) using distributed tracing with trace ID
- **SC-014**: All critical metrics (API latency, Kafka lag, error rates) are visible in Grafana dashboards with 30-second refresh intervals
- **SC-015**: Alerts fire within 1 minute when SLA violations occur (error rate >5%, consumer lag >10K messages, database connection pool >90% utilized)
- **SC-016**: 90% of production incidents can be diagnosed using existing observability tools (metrics, traces, logs) without needing to add new instrumentation

**Data Integrity**:
- **SC-017**: Duplicate message submissions with the same message_id are rejected or deduplicated 100% of the time (idempotency guarantee)
- **SC-018**: Messages within the same conversation maintain send order 100% of the time when processed through the pipeline
- **SC-019**: Abandoned file uploads (>24 hours old) are cleaned up automatically within 1 hour of the daily cron job execution, recovering storage space

**Resilience**:
- **SC-020**: PostgreSQL automatic failover completes within 30 seconds of primary node failure, with <5 seconds of write unavailability
- **SC-021**: Kafka cluster continues accepting messages with zero data loss when 1 out of 3 brokers fails
- **SC-022**: API continues serving requests with <1% error rate when 1 out of 3 API pods crashes

## Assumptions

1. **Infrastructure**: Production deployment will be on Kubernetes (GKE, EKS, AKS, or self-hosted) with sufficient resources for 3+ replicas of each service
2. **Database**: PostgreSQL will use an operator like Patroni, Stolon, or cloud-managed solutions (RDS, Cloud SQL) for automatic failover
3. **Load**: Initial production load will be <1M messages/day, scaling to 10M messages/minute peak within 6-12 months
4. **File Storage**: MinIO will be deployed with distributed mode (4+ nodes) or replaced with S3/GCS/Azure Blob for production
5. **Network**: Internal service-to-service communication will be reliable (low latency, no partitions). External client connections may be unreliable (mobile networks)
6. **Authentication**: OAuth 2.0 Client Credentials flow with JWT tokens (15-minute expiration, refresh tokens for extended sessions) will be implemented in this phase
7. **gRPC Usage**: gRPC will be used exclusively for internal service-to-service communication to optimize high-volume internal message passing; REST remains the primary external API
8. **External Connectors**: Mock connectors simulating WhatsApp, Instagram, Telegram, and Messenger will be used; real external platform integration requires separate business agreements and API approval processes
9. **Tenancy Model**: Single-tenant architecture with one isolated deployment per customer organization (Kubernetes namespace with dedicated resources); no shared multi-tenant infrastructure
10. **Monitoring Budget**: Organization has Prometheus, Grafana, and Jaeger licenses or is using open-source versions
11. **Team Skills**: Development team has familiarity with Python, FastAPI, Kafka, Kubernetes, OAuth 2.0, and observability patterns
12. **Data Retention**: Message history will be retained indefinitely unless a future data retention policy is implemented
13. **Geographic Distribution**: Initial deployment will be in a single region; multi-region support is out of scope for this specification

## Out of Scope

- **Multi-region deployment**: Active-active or active-passive cross-region setups are not included
- **Multi-tenancy infrastructure**: Shared database/infrastructure for multiple customer organizations is not implemented; single-tenant model only
- **External gRPC API**: gRPC is used for internal service communication only; no external gRPC API for clients (REST only)
- **Real external platform connectors**: WhatsApp Business API, Facebook Graph API, Telegram Bot API integration is deferred; mock connectors only
- **Third-party Identity Providers**: OIDC/SAML integration with external IdPs (Google, Okta, Azure AD) is not implemented
- **User registration/management**: Self-service user registration, password reset, email verification, and user invitation flows are deferred
- **End-to-end encryption**: While TLS secures transport, end-to-end encrypted messaging (like Signal protocol) is not implemented
- **Mobile push notifications**: iOS/Android push notifications for offline users are not included
- **Voice/video calling**: Real-time voice and video are out of scope
- **Message search**: Full-text search across message history (conversation-scoped or global) is deferred to future phase
- **User presence**: Online/offline/typing indicators are not included
- **Message editing/deletion**: Editing or deleting sent messages is not supported
- **Rich media support**: Embedding previews for links, images, videos is not included
- **Bot framework**: No API for chatbots or automated message processing
- **Webhook notifications**: Event-driven webhooks for external system integration are not implemented
- **GDPR tooling**: Automated GDPR compliance tools (data export, deletion requests) are not implemented
- **Performance testing framework**: While performance requirements are specified, automated load testing infrastructure is not included
