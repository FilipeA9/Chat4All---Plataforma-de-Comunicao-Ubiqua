# Tasks: Production-Ready Platform Evolution

**Input**: Design documents from `/specs/002-production-ready/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (all complete)

**Organization**: Tasks are organized by user story to enable independent implementation and testing. This follows the 5-phase breakdown:
- **Phase 1**: Foundational Reliability and Data Consistency
- **Phase 2**: High-Availability Infrastructure
- **Phase 3**: Core Features (Authentication, Real-Time, File Upload, API Enhancements)
- **Phase 4**: Observability and Security
- **Phase 5**: Performance Validation

**Tests**: Tests are NOT included per feature specification requirements. Focus is on implementation and validation scenarios from user stories.

---

## Format: `- [ ] [ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5, US6)
- All file paths are absolute from repository root

---

## Phase 1: Setup & Initial Configuration

**Purpose**: Project initialization and basic infrastructure setup

- [X] T001 Verify project structure matches plan.md (hexagonal architecture with auth/, outbox/, websocket/, observability/ modules)
- [X] T002 Update requirements.txt with production dependencies (authlib, redis, websockets, prometheus-client, opentelemetry-api, opentelemetry-sdk, locust)
- [X] T003 [P] Create .env.production template with OAuth 2.0 secrets (JWT_SECRET_KEY, JWT_ALGORITHM=RS256, ACCESS_TOKEN_EXPIRE_MINUTES=15, REFRESH_TOKEN_EXPIRE_DAYS=30)
- [X] T004 [P] Configure Docker Compose to remove container_name fields for horizontal scaling (allow docker-compose up --scale)
- [X] T005 Setup local Redis instance for Pub/Sub, rate limiting, and deduplication (redis:7-alpine container in docker-compose.yml)

---

## Phase 2: Foundational Infrastructure (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story implementation begins

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Principle II - Reliability & Resilience

- [X] T006 Create database migration 003_production_ready.sql with all production tables (access_tokens, refresh_tokens, outbox_events, files, file_chunks, websocket_connections)
- [X] T007 [P] Add UNIQUE constraints for idempotency (messages.id, outbox_events.aggregate_id+event_type, file_chunks.upload_id+chunk_number)
- [X] T008 [P] Create indexes for performance (access_tokens.token_hash, outbox_events.published+created_at, files.status+created_at)
- [X] T009 [P] Implement database connection pooling in db/database.py (SQLAlchemy pool_size=20, max_overflow=10, pool_pre_ping=True)

### Principle III - Scalability & Performance

- [X] T010 [P] Configure Kafka topics with high partitioning (messages: 100 partitions, file_merge_requests: 50 partitions, message_status_updates: 50 partitions)
- [X] T011 [P] Setup Kafka producer with idempotent configuration (enable.idempotence=true, acks=all, retries=5, max.in.flight.requests=5)
- [X] T012 [P] Implement stateless API design verification (remove any in-memory state, use Redis for rate limiting and session data)

### Principle VI - Security & Privacy

- [X] T013 [P] Implement JWT token generation in core/security.py (RS256 algorithm, 15min expiration, claims: user_id, tenant_id, iat, exp, scope)
- [X] T014 [P] Create OAuth 2.0 authentication middleware in api/dependencies.py (validate Bearer token, verify signature, check expiration)
- [X] T015 [P] Setup TLS 1.3 for FastAPI endpoints (update docker-compose.yml with SSL certificates, enforce HTTPS redirects)
- [X] T016 Implement rate limiting middleware using Redis (60 req/min per user for state-changing endpoints, sliding window algorithm)
- [X] T017 [P] Create audit logging for security events in core/audit_logger.py (authentication failures, token revocation, rate limit violations)

### Principle VII - Observability

- [X] T018 [P] Setup Prometheus metrics exporters in all services (api/metrics.py, workers/metrics.py with Counter, Histogram, Gauge)
- [X] T019 [P] Implement OpenTelemetry tracing in main.py (tracer initialization, context propagation via Kafka headers)
- [X] T020 [P] Configure structured JSON logging with mandatory fields (timestamp, level, service, trace_id, request_id, message) in core/logging_config.py
- [X] T021 [P] Create health check endpoints (GET /health for liveness, GET /ready for readiness with DB/Redis/Kafka checks)
- [X] T022 Setup Prometheus configuration file (prometheus.yml) with scrape targets for API and workers (scrape_interval=15s)
- [X] T023 [P] Setup Grafana dashboard JSON files in observability/ (api_health.json, message_pipeline.json, kafka_lag.json, database_performance.json)
- [X] T024 [P] Configure Alertmanager rules for critical conditions (error_rate>5%, kafka_lag>10000, db_pool_utilization>90%)

### Core Domain Infrastructure

- [X] T025 Extend Message entity in db/models.py with outbox support (add helper method to create outbox event in same transaction)
- [X] T026 [P] Create OutboxEvent entity in db/models.py per data-model.md (aggregate_type, aggregate_id, event_type, payload JSONB, published, version, error_message)
- [X] T027 [P] Create AccessToken and RefreshToken entities in db/models.py per data-model.md (token_hash SHA-256, expiration, revocation fields)

**Checkpoint**: Foundation ready - all infrastructure is in place, user story implementation can now begin in parallel

---

## Phase 3: User Story 2 - Resilient Message Processing (Priority: P1) 🎯 MVP

**Goal**: Implement Transactional Outbox pattern to guarantee at-least-once message delivery with zero data loss

**Independent Test**: Shut down Kafka broker mid-transaction → verify message is persisted in outbox_events → restart Kafka → confirm message is eventually published and processed

**Epic**: Epic 2 - Resilient and Consistent Data Plane (FR-DP-01 to FR-DP-10)

### Task 1.1: Implement Transactional Outbox Pattern

- [X] T028 [US2] Create outbox_events table in migration 003_production_ready.sql (id, aggregate_type, aggregate_id, event_type, payload JSONB, published, published_at, created_at, version, error_message)
- [X] T029 [US2] Modify POST /v1/messages endpoint in api/endpoints.py to write to messages AND outbox_events in single transaction (use SQLAlchemy session.begin())
- [X] T030 [US2] Create OutboxPoller worker in workers/outbox_poller.py (poll unpublished events every 500ms, publish to Kafka, mark as published, handle errors with exponential backoff)
- [X] T031 [US2] Implement exponential backoff in outbox poller (initial delay 1s, max 3 retries, increment version field, update error_message on failure)

**Acceptance**: POST /v1/messages returns 202 Accepted → Kafka down → message in outbox_events with published=FALSE → Kafka up → poller publishes → message appears in conversation

### Task 1.2: Implement Idempotency and Deduplication

- [X] T032 [P] [US2] Add UNIQUE constraint on messages.id in 003_production_ready.sql (enforce database-level deduplication)
- [X] T033 [P] [US2] Implement message deduplication cache in Redis (key=message:id:{uuid}, TTL=24h, store minimal metadata)
- [X] T034 [US2] Update message workers in workers/message_router.py to use INSERT ... ON CONFLICT DO NOTHING (idempotent writes)
- [X] T035 [US2] Add idempotency middleware in api/dependencies.py (check Redis cache before processing, return 200 OK with cached response if duplicate)

**Acceptance**: Duplicate message submission with same message.id → 200 OK returned immediately, no database write, cached response

### Task 1.3: Implement Dead Letter Queue (DLQ)

- [X] T036 [US2] Create Kafka topic message_processing_dlq (3 partitions, RF=3, retention=7d) via Kafka admin API in services/kafka_producer.py
- [X] T037 [US2] Implement DLQ publisher in workers/message_router.py (after 3 failed retries, publish to message_processing_dlq with failure metadata)
- [X] T038 [US2] Add DLQ monitoring in workers/metrics.py (Prometheus counter dlq_messages_total with labels: reason, aggregate_type)
- [X] T039 [US2] Create alert rule in observability/prometheus_rules.yml (trigger when dlq_messages_total increases, route to Alertmanager)

**Acceptance**: Message fails after 3 retries → published to message_processing_dlq → alert fired → SRE investigates using Grafana + Jaeger

### Task 1.4: Ensure Message Ordering within Conversations

- [X] T040 [US2] Update Kafka producer in services/kafka_producer.py to use conversation_id as partition key (ensures same conversation → same partition → ordering)
- [X] T041 [US2] Configure Kafka consumer in workers/message_router.py with enable.auto.commit=false, commit offsets only after successful DB write
- [X] T042 [US2] Add message sequence verification in workers/message_router.py (detect out-of-order processing, log warning, optionally reorder before DB insert)
- [X] T043 [US2] Create integration test script in tests/integration/test_message_ordering.py (send 100 messages to same conversation concurrently, verify DB order matches send order)

**Acceptance**: Send 100 messages to conversation X concurrently → all messages processed → database query shows correct chronological order (created_at ascending)

**Checkpoint**: User Story 2 (Resilient Message Processing) is fully functional and independently testable

---

## Phase 4: User Story 3 - Zero-Downtime Infrastructure (Priority: P2)

**Goal**: Implement high-availability infrastructure to survive single component failures with automatic failover

**Independent Test**: Run load test → kill PostgreSQL primary → verify replica promotion within 30s → kill Kafka broker → verify messages continue processing → kill API pod → verify traffic routes to healthy instances

**Epic**: Epic 3 - Scalable and Fault-Tolerant Infrastructure (FR-HA-01 to FR-HA-09)

### Task 2.1: Configure PostgreSQL High Availability

- [ ] T044 [US3] Create docker-compose.patroni.yml with Patroni cluster (1 primary + 2 replicas, etcd for consensus, shared volume for WAL)
- [ ] T045 [US3] Configure Patroni bootstrap configuration (postgresql.conf with synchronous_commit=on, max_wal_senders=5, wal_level=replica)
- [ ] T046 [US3] Setup Patroni REST API health checks (GET /health, GET /leader for primary detection)
- [ ] T047 [US3] Update application db/database.py to use Patroni cluster endpoint (HAProxy or pgbouncer in front of Patroni cluster)
- [ ] T048 [US3] Implement automatic connection retry in db/database.py (detect failover via connection errors, retry with exponential backoff up to 30s)

**Acceptance**: Kill PostgreSQL primary pod → Patroni promotes replica within 30s → application reconnects automatically → POST /v1/messages continues working with <5s write unavailability

### Task 2.2: Deploy Kafka as High-Availability Cluster

- [X] T049 [US3] Create docker-compose.kafka-cluster.yml with 3 Kafka brokers (kafka-1, kafka-2, kafka-3, ZooKeeper ensemble)
- [X] T050 [US3] Configure all Kafka topics with replication.factor=3, min.insync.replicas=2 (via Kafka admin API in setup script)
- [X] T051 [US3] Update Kafka producers in services/kafka_producer.py to use all 3 broker addresses (bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092)
- [X] T052 [US3] Implement Kafka broker health monitoring in workers/metrics.py (check under-replicated partitions, offline partitions, ISR shrink events)

**Acceptance**: Kill kafka-2 broker → messages continue publishing to kafka-1 and kafka-3 → no data loss → kafka-2 restarts → partitions resync automatically

### Task 2.3: Implement Kubernetes Deployment with Auto-Scaling

- [ ] T053 [US3] Create Kubernetes manifests in k8s/ (api-deployment.yaml with 3 replicas, worker-deployment.yaml with 5 replicas, services, ingress)
- [ ] T054 [US3] Configure HorizontalPodAutoscaler for API (target CPU 70%, min 3 replicas, max 10 replicas, scaleDown stabilization 300s)
- [ ] T055 [US3] Configure HorizontalPodAutoscaler for workers (target CPU 70%, min 5 replicas, max 20 replicas)
- [ ] T056 [US3] Setup liveness and readiness probes in deployments (livenessProbe: GET /health, readinessProbe: GET /ready with DB check)
- [ ] T057 [US3] Create Kubernetes Service for API with type LoadBalancer (distributes traffic across all healthy API pods)

**Acceptance**: Simulate CPU spike (load test) → HPA scales API from 3 to 7 pods within 60s → load decreases → HPA scales down to 3 pods after 5min stabilization

### Task 2.4: Implement Circuit Breakers and Graceful Degradation

- [X] T058 [P] [US3] Implement circuit breaker for Kafka in services/kafka_producer.py (using pybreaker library, failure threshold=5, timeout=60s, half-open after 30s)
- [X] T059 [P] [US3] Implement circuit breaker for Redis in services/redis_client.py (failure threshold=3, timeout=30s)
- [X] T060 [US3] Add fallback behavior in api/endpoints.py (if Kafka circuit open, queue in Redis list and return 202 Accepted with warning header)
- [X] T061 [US3] Create background job in workers/redis_backfill.py (poll Redis fallback queue every 10s, attempt to publish to Kafka when circuit closes)

**Acceptance**: Kafka down → circuit opens after 5 failures → API continues accepting messages (queued in Redis) → Kafka up → circuit half-opens → backfill worker publishes queued messages

**Checkpoint**: User Story 3 (Zero-Downtime Infrastructure) is fully functional - system survives all single-component failures

---

## Phase 5: User Story 1 - Real-Time Message Notifications (Priority: P1)

**Goal**: Implement WebSocket connections with Redis Pub/Sub for real-time message delivery across multiple API instances

**Independent Test**: Open two browser windows → User A sends message → User B receives notification in <100ms without page refresh

**Epic**: Epic 1 - Real-Time Communication Layer (FR-RT-01 to FR-RT-07)

### Task 3.1: Implement WebSocket Connection Management

- [X] T062 [US1] Create WebSocket endpoint /ws in api/endpoints.py (FastAPI WebSocket route with JWT authentication via query param ?token={jwt})
- [X] T063 [US1] Implement ConnectionManager in api/websocket_manager.py (track active connections: Dict[user_id, List[WebSocket]], subscribe to conversations)
- [X] T064 [US1] Add JWT validation for WebSocket connections in api/dependencies.py (decode token, verify signature, check expiration before accepting connection)
- [X] T065 [US1] Implement heartbeat mechanism (send ping every 30s, expect pong within 10s, close stale connections)
- [X] T066 [US1] Add WebSocket connection metrics in api/metrics.py (Gauge websocket_connections_active, Counter websocket_connections_total, Histogram websocket_message_latency_seconds)

**Acceptance**: User connects to ws://api/ws?token={valid_jwt} → connection accepted → GET /metrics shows websocket_connections_active=1

### Task 3.2: Implement Redis Pub/Sub for Multi-Instance Fan-Out

- [X] T067 [US1] Setup Redis Pub/Sub subscriber in api/redis_subscriber.py (subscribe to channels: conversation:{id}, user:{id}, global)
- [X] T068 [US1] Integrate Redis subscriber with ConnectionManager (on message received from Redis, lookup user's WebSocket connections, send to all)
- [X] T069 [US1] Update outbox poller in workers/outbox_poller.py to publish to Redis Pub/Sub after Kafka publish (PUBLISH conversation:{id} with event payload)
- [X] T070 [US1] Implement channel subscription management (when user connects, SUBSCRIBE to conversation:{conversation_id} for all user's conversations)

**Acceptance**: 3 API instances running → User A connected to instance 1 → User B connected to instance 2 → User A sends message → both receive notification via Redis Pub/Sub

### Task 3.3: Implement Real-Time Event Broadcasting

- [X] T071 [P] [US1] Define WebSocket message schemas in api/schemas.py (MessageCreated, MessageDelivered, MessageRead, ConversationRead events)
- [X] T072 [US1] Update POST /v1/messages endpoint to publish MessageCreated event to Redis after outbox write (PUBLISH conversation:{id})
- [X] T073 [US1] Create POST /v1/conversations/{id}/read endpoint in api/endpoints.py (mark messages as READ, publish ConversationRead event to Redis)
- [X] T074 [US1] Implement message status update worker in workers/message_status_updater.py (consume Kafka topic, update DB, publish to Redis)

**Acceptance**: User A sends message → User B receives MessageCreated event in <100ms → User B calls POST /conversations/{id}/read → User A receives ConversationRead event

### Task 3.4: Optimize WebSocket Performance for 10K Connections

- [X] T075 [US1] Implement connection pooling for Redis Pub/Sub (use redis-py ConnectionPool with max_connections=50)
- [X] T076 [US1] Add connection limiting per user in api/websocket_manager.py (max 5 concurrent connections per user_id to prevent abuse)
- [X] T077 [US1] Optimize subscription management (batch SUBSCRIBE commands, use Redis pipelining to reduce round trips)
- [X] T078 [US1] Create load test script in tests/load/websocket_load_test.py (using Locust WebSocketUser, simulate 10K concurrent connections, measure latency)

**Acceptance**: Load test establishes 10K WebSocket connections per API instance → CPU usage <70% → send 100 msg/s → p99 notification latency <100ms

**Checkpoint**: User Story 1 (Real-Time Message Notifications) is fully functional - users receive instant notifications

---

## Phase 6: User Story 4 - Resumable Large File Uploads (Priority: P2)

**Goal**: Implement chunked file uploads with resumability for files up to 2GB

**Independent Test**: Upload 1GB file → simulate network interruption at 500MB → resume upload from chunk 501 → verify complete file in MinIO

**Epic**: Epic 4 - Full-Featured File Upload (FR-FU-01 to FR-FU-10)

### Task 3.5: Implement Chunked Upload Endpoints

- [X] T079 [P] [US4] Create File and FileChunk entities in db/models.py per data-model.md (upload_id, user_id, filename, total_size_bytes, total_chunks, chunk_size, status, chunks_received JSON)
- [X] T080 [US4] Implement POST /v1/files/initiate endpoint in api/endpoints.py (validate file_size ≤2GB, calculate total_chunks, return upload_id)
- [X] T081 [US4] Implement POST /v1/files/{upload_id}/chunks endpoint in api/endpoints.py (accept chunk_number query param, validate chunk_number, store in MinIO, update chunks_received array)
- [X] T082 [US4] Implement GET /v1/files/{upload_id}/status endpoint in api/endpoints.py (return uploaded_chunks, total_chunks, percentage, missing_chunks)
- [X] T083 [US4] Implement POST /v1/files/{upload_id}/complete endpoint in api/endpoints.py (validate all chunks received, change status to MERGING, publish file_merge_request to Kafka, return 202 Accepted)

**Acceptance**: POST /v1/files/initiate with size=1073741824 → returns upload_id, total_chunks=107 (10MB chunks) → upload 107 chunks → POST /complete → 202 Accepted

### Task 3.6: Implement Chunk Merge Worker

- [X] T084 [US4] Create file merge worker in workers/file_merge_worker.py (consume file_merge_request topic, retrieve all chunks from MinIO, compose into single file)
- [X] T085 [US4] Implement MinIO multipart upload compose in services/minio_client.py (use minio.compose_object() to merge chunks server-side)
- [X] T086 [US4] Update file status to COMPLETED after successful merge in workers/file_merge_worker.py (update files table, delete chunk records, publish FileUploadCompleted event)
- [X] T087 [US4] Implement chunk cleanup in workers/file_merge_worker.py (delete individual chunk objects from MinIO after successful merge)

**Acceptance**: Upload completes → worker consumes event → chunks merged into files/{upload_id}/original.ext in MinIO → chunks deleted → file status=COMPLETED

### Task 3.7: Implement Resumability and Progress Tracking

- [X] T088 [US4] Add chunk validation in POST /v1/files/{upload_id}/chunks (check chunk_number not already uploaded, verify chunk hash if provided)
- [X] T089 [US4] Implement retry logic for chunk uploads in client example (exponential backoff, max 5 retries per chunk)
- [X] T090 [US4] Update GET /v1/files/{upload_id}/status to return missing_chunks array (chunks 1-total_chunks not in chunks_received)
- [X] T091 [US4] Create upload resume logic in client example (call GET /status to get missing_chunks, upload only missing chunks)

**Acceptance**: Upload 50 out of 100 chunks → network failure → client calls GET /status → receives missing_chunks=[51-100] → resumes upload from chunk 51

### Task 3.8: Implement Garbage Collection for Abandoned Uploads

- [X] T092 [US4] Create daily cron job worker in workers/upload_garbage_collector.py (query files with status=UPLOADING AND created_at < NOW() - INTERVAL '24 hours')
- [X] T093 [US4] Implement cleanup logic (delete file_chunks from DB, delete chunk objects from MinIO using minio.remove_objects(), update file status to FAILED)
- [X] T094 [US4] Add garbage collection metrics in workers/metrics.py (Counter uploads_cleaned_total, Histogram cleanup_duration_seconds)
- [X] T095 [US4] Schedule cron job in Kubernetes (CronJob resource in k8s/cronjobs.yaml, schedule: "0 2 * * *" for 2 AM daily)

**Acceptance**: Upload initiated 25 hours ago, only 10 chunks uploaded → cron job runs → chunks deleted from MinIO and DB → file status=FAILED

**Checkpoint**: User Story 4 (Resumable Large File Uploads) is fully functional - users can upload 2GB files with resume capability

---

## Phase 7: User Story 5 - Conversation Discovery and Management (Priority: P3)

**Goal**: Implement conversation listing with pagination and read receipts

**Independent Test**: Create 50 conversations → call GET /v1/conversations → verify returned in order of most recent message, paginated

**Epic**: Epic 5 - Enhanced API Functionality (FR-API-01 to FR-API-09)

### Implementation for User Story 5

- [X] T096 [P] [US5] Create ConversationView materialized view in 003_production_ready.sql (conversation_id, user_id, last_message_timestamp, last_message_content, unread_count, optimized with JOIN on messages)
- [X] T097 [US5] Implement GET /v1/conversations endpoint in api/endpoints.py (query ConversationView, ORDER BY last_message_timestamp DESC, support limit/offset pagination)
- [X] T098 [US5] Optimize GET /v1/conversations query to avoid N+1 (use SQLAlchemy joinedload or selectinload to fetch conversation metadata in single query)
- [X] T099 [US5] Implement POST /v1/conversations/{id}/read endpoint in api/endpoints.py (UPDATE messages SET status='READ' WHERE conversation_id={id}, publish ConversationRead event to Redis)
- [X] T100 [US5] Add rate limiting to conversation endpoints (apply rate_limit_middleware from core/middleware.py, 60 req/min per user)
- [X] T101 [US5] Update GET /v1/conversations response schema in api/schemas.py (ConversationListResponse with items, total, limit, offset, has_more pagination metadata)

**Acceptance**: GET /v1/conversations?limit=20&offset=0 → returns 20 conversations sorted by recent activity in <100ms → POST /conversations/{id}/read → all messages marked READ → WebSocket clients receive ConversationRead event

**Checkpoint**: User Story 5 (Conversation Discovery) is fully functional - users can list and manage conversations efficiently

---

## Phase 8: User Story 6 - Full Observability for Operations (Priority: P3)

**Goal**: Implement production-grade observability with metrics, traces, logs, and dashboards

**Independent Test**: Generate load → view Grafana dashboards → search for message by trace_id in Jaeger → verify all spans appear → query logs by trace_id in Loki

**Epic**: Epic 6 - Production-Grade Observability (FR-OBS-01 to FR-OBS-10)

### Task 4.1: Integrate Prometheus Metrics Collection

- [X] T102 [P] [US6] Instrument FastAPI with prometheus-fastapi-instrumentator in main.py (automatically expose request_duration_seconds, request_count, etc.)
- [X] T103 [P] [US6] Add custom business metrics in api/metrics.py (Counter messages_created_total, Histogram message_processing_duration_seconds, Gauge outbox_pending_events)
- [X] T104 [P] [US6] Add Kafka consumer lag metrics in workers/metrics.py (Gauge kafka_consumer_lag{topic, partition, consumer_group})
- [X] T105 [P] [US6] Add database connection pool metrics in db/database.py (Gauge db_pool_connections_active, Gauge db_pool_connections_idle, Counter db_queries_total)
- [X] T106 [US6] Deploy Prometheus in docker-compose.yml (prom/prometheus:latest, volume mount prometheus.yml, expose port 9090)

**Acceptance**: Access http://localhost:9090 → query http_requests_total → see API request counts → query kafka_consumer_lag → see current lag per topic

### Task 4.2: Implement Distributed Tracing with OpenTelemetry

- [X] T107 [US6] Initialize OpenTelemetry tracer in main.py (use opentelemetry.sdk.trace.TracerProvider, configure Jaeger exporter)
- [X] T108 [US6] Instrument FastAPI with OpenTelemetry in main.py (use opentelemetry.instrumentation.fastapi, auto-instrument all endpoints)
- [X] T109 [US6] Propagate trace context via Kafka headers in services/kafka_producer.py (inject trace context into Kafka message headers using W3C Trace Context format)
- [X] T110 [US6] Extract trace context in workers in workers/message_router.py (extract from Kafka headers, continue trace span in worker processing)
- [X] T111 [US6] Add custom spans for key operations (with tracer.start_as_current_span(), span for DB queries, span for Redis operations, span for MinIO uploads)
- [X] T112 [US6] Deploy Jaeger in docker-compose.yml (jaegertracing/all-in-one:latest, expose UI on port 16686, configure OpenTelemetry to export to Jaeger)

**Acceptance**: POST /v1/messages → trace_id logged in response → search trace_id in Jaeger UI → see spans: API ingestion → Kafka publish → Worker processing → DB write (total 4+ spans)

### Task 4.3: Centralize Logging and Configure Alerting

- [X] T113 [P] [US6] Implement structured JSON logging in core/logging_config.py (use python-json-logger, include trace_id, request_id, user_id, timestamp, level, message)
- [X] T114 [P] [US6] Configure log correlation in api/dependencies.py (extract trace_id from OpenTelemetry context, inject into logger context for all logs in request)
- [X] T115 [US6] Deploy Loki in docker-compose.yml (grafana/loki:latest, expose port 3100, configure Promtail to ship logs from all containers)
- [X] T116 [US6] Create Grafana dashboards in observability/ (api_health.json: latency, throughput, error rate; message_pipeline.json: Kafka lag, worker throughput; kafka_lag.json: per-topic lag; database_performance.json: query latency, pool utilization)
- [X] T117 [US6] Import Grafana dashboards in docker-compose.yml (grafana/grafana:latest, volume mount dashboards, configure datasources for Prometheus, Loki, Jaeger)
- [X] T118 [US6] Configure Alertmanager in observability/alertmanager.yml (routes: critical alerts to PagerDuty, warnings to Slack, notifications to email)
- [X] T119 [US6] Create Prometheus alert rules in observability/prometheus_rules.yml (APIErrorRateHigh: rate(http_requests_total{status=~"5.."}[5m]) > 0.05, KafkaConsumerLagHigh: kafka_consumer_lag > 10000, DatabasePoolExhausted: db_pool_connections_active / (db_pool_connections_active + db_pool_connections_idle) > 0.9)

**Acceptance**: API error rate exceeds 5% → Prometheus evaluates rule → alert fires → Alertmanager sends to Slack → SRE investigates using Grafana → drills down by trace_id in Jaeger → finds root cause in Loki logs

**Checkpoint**: User Story 6 (Full Observability) is fully functional - SREs have complete visibility into system health

---

## Phase 9: Epic 0 - Authentication and Authorization (Foundation)

**Goal**: Implement OAuth 2.0 Client Credentials flow with JWT tokens for API authentication

**Epic**: Epic 0 - Authentication and Authorization (FR-AUTH-01 to FR-AUTH-10)

### Implementation for Authentication

- [X] T120 [P] Create POST /auth/token endpoint in api/endpoints.py (accept client_id, client_secret, grant_type=client_credentials, return access_token + refresh_token)
- [X] T121 [P] Implement JWT token generation in core/security.py (use authlib JWTEncodingBackend, RS256 algorithm, claims: user_id, tenant_id, iat, exp, scope, 15min expiration)
- [X] T122 [P] Create POST /auth/refresh endpoint in api/endpoints.py (accept refresh_token, validate token_hash in DB, return new access_token)
- [X] T123 [P] Implement POST /auth/revoke endpoint in api/endpoints.py (accept refresh_token, update refresh_tokens.revoked=TRUE, return 204 No Content)
- [X] T124 Update all protected endpoints to require Bearer token authentication (apply Depends(get_current_user) to all routes in api/endpoints.py)
- [X] T125 [P] Create access token revocation check in api/dependencies.py (query access_tokens table, check revoked=FALSE AND expires_at > NOW())
- [X] T126 [P] Implement refresh token rotation in POST /auth/refresh (optional enhancement: invalidate old refresh_token, issue new refresh_token)

**Acceptance**: POST /auth/token with valid client_id/client_secret → returns access_token + refresh_token → use access_token for POST /v1/messages → 200 OK → wait 16 minutes → 401 Unauthorized → POST /auth/refresh with refresh_token → new access_token → use new token → 200 OK

**Checkpoint**: Authentication is fully functional - all API endpoints protected by OAuth 2.0

---

## Phase 10: Performance Validation and Final Testing

**Goal**: Validate all performance targets from NFR requirements are met under load

### Task 5.1: Execute Load Testing

- [X] T127 Create Locust load test suite in tests/load/ (test_api_throughput.py: 10M msg/min, test_websocket_connections.py: 10K concurrent connections, test_file_upload.py: 2GB chunked upload)
- [X] T128 Execute API latency load test (10K req/s, measure p99 latency, target <200ms from ingestion to Kafka publish)
- [X] T129 Execute WebSocket scalability load test (establish 10K connections per instance, send 100 msg/s, measure notification delivery latency, target <100ms)
- [X] T130 Execute file upload load test (100 concurrent 1GB file uploads, measure chunk upload latency, target <5s per 10MB chunk)
- [X] T131 Execute message throughput load test (ramp to 10M msg/min, measure Kafka producer latency, worker processing latency, database write latency, ensure no bottlenecks)

**Acceptance**: All load tests pass with targets met (API p99 <200ms, WebSocket latency <100ms, file upload <5s per chunk, 10M msg/min sustained)

### Task 5.2: Document Findings and Prepare Final Report

- [ ] T132 Analyze load test results (identify bottlenecks, document actual vs target performance, create performance baseline report in docs/performance_report.md)
- [ ] T133 Execute chaos engineering experiments (kill PostgreSQL primary, kill Kafka broker, kill API pod, network partition between services, measure MTTR and data loss)
- [ ] T134 Document chaos experiment results (validate 30s PostgreSQL failover, zero data loss with Kafka broker failure, automatic traffic rerouting with API pod failure)
- [ ] T135 Verify all 22 success criteria from spec.md (SC-001 to SC-022, document pass/fail for each, create traceability matrix in docs/success_criteria_matrix.md)
- [ ] T136 Update quickstart.md with final setup instructions (incorporate all production features, update environment variables, add troubleshooting section)
- [ ] T137 Create production deployment guide in docs/production_deployment.md (Kubernetes manifests, Helm charts, database migration procedures, monitoring setup, disaster recovery runbook)

**Acceptance**: Performance report shows all NFR targets met → Chaos experiments demonstrate resilience → All 22 success criteria validated → Documentation complete and reviewed

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Final improvements affecting multiple user stories

- [ ] T138 [P] Add API documentation with OpenAPI schema generation (use FastAPI auto-docs, add detailed descriptions to all endpoints in api/endpoints.py)
- [ ] T139 [P] Implement request/response logging middleware (log all requests with trace_id, user_id, method, path, status_code, duration_ms)
- [ ] T140 Security hardening (run OWASP dependency check, update all dependencies to latest secure versions, configure security headers: HSTS, CSP, X-Content-Type-Options)
- [ ] T141 [P] Code cleanup and refactoring (remove dead code, standardize error handling, ensure consistent naming conventions)
- [ ] T142 Add end-to-end integration test suite in tests/e2e/ (test complete user journeys: signup → authenticate → send message → receive WebSocket notification → upload file → list conversations)
- [ ] T143 Run quickstart.md validation (execute all steps from scratch on clean VM, verify all services start, all test scenarios pass, document actual setup time)
- [ ] T144 Create video demo recording (demonstrate real-time messaging, file upload resume, high availability failover, observability dashboards, <10 minute overview)

---

## Dependencies & Execution Order

### Phase Dependencies

1. **Phase 1 (Setup)**: No dependencies - can start immediately
2. **Phase 2 (Foundational)**: Depends on Phase 1 completion - **BLOCKS all user stories**
3. **Phase 3 (US2 - Resilient Processing)**: Depends on Phase 2 - P1 priority, implements Transactional Outbox (blocking for other stories)
4. **Phase 4 (US3 - Zero-Downtime)**: Depends on Phase 2 - P2 priority, can start after Phase 2 completes (parallel to Phase 5)
5. **Phase 5 (US1 - Real-Time)**: Depends on Phase 2 and Phase 3 (needs Outbox for event publishing) - P1 priority
6. **Phase 6 (US4 - File Upload)**: Depends on Phase 2 - P2 priority, can run parallel to Phases 4-5
7. **Phase 7 (US5 - Conversation Discovery)**: Depends on Phase 2, Phase 5 (needs WebSocket for read receipts) - P3 priority
8. **Phase 8 (US6 - Observability)**: Depends on Phase 2 - P3 priority, can start early (parallel implementation)
9. **Phase 9 (Authentication)**: Depends on Phase 2 - Foundation epic, should complete early (parallel to Phases 3-4)
10. **Phase 10 (Performance Validation)**: Depends on Phases 3-9 completion - validates all functionality
11. **Phase 11 (Polish)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US2 (Resilient Processing - P1)**: No dependencies on other user stories, only on Foundational phase
- **US3 (Zero-Downtime - P2)**: No dependencies on other user stories, only on Foundational phase
- **US1 (Real-Time - P1)**: Depends on US2 (needs Outbox pattern for event publishing)
- **US4 (File Upload - P2)**: No dependencies on other user stories, only on Foundational phase
- **US5 (Conversation Discovery - P3)**: Depends on US1 (WebSocket integration for read receipts)
- **US6 (Observability - P3)**: No dependencies on other user stories, can instrument all components progressively

### Critical Path (for MVP)

**MVP = US2 (Resilient Processing) + US1 (Real-Time)**

1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T027) ← **CRITICAL BLOCKER**
3. Complete Phase 3: US2 - Resilient Processing (T028-T043)
4. Complete Phase 5: US1 - Real-Time (T062-T078)
5. Complete Phase 9: Authentication (T120-T126)
6. Validate MVP functionality

### Within Each User Story

- Foundational tasks (T006-T027) MUST complete before any user story tasks
- For US2: T028-T031 (Outbox) → T032-T035 (Idempotency) → T036-T039 (DLQ) → T040-T043 (Ordering)
- For US1: T062-T066 (WebSocket) → T067-T070 (Redis Pub/Sub) → T071-T074 (Event Broadcasting) → T075-T078 (Performance)
- For US4: T079-T083 (Endpoints) → T084-T087 (Merge Worker) → T088-T091 (Resumability) → T092-T095 (Garbage Collection)

### Parallel Opportunities

**After Foundational Phase (T006-T027) completes:**

- **Parallel Group 1** (different epics, no dependencies):
  - US2 - Resilient Processing (T028-T043)
  - US3 - Zero-Downtime (T044-T061)
  - US6 - Observability (T102-T119)
  - Epic 0 - Authentication (T120-T126)

- **Parallel Group 2** (after US2 completes):
  - US1 - Real-Time (T062-T078, depends on US2)
  - US4 - File Upload (T079-T095, independent)

- **Parallel Group 3** (after US1 completes):
  - US5 - Conversation Discovery (T096-T101, depends on US1)

**Within Foundational Phase** (can parallelize marked with [P]):
- Security tasks (T013-T017) can run parallel to Observability tasks (T018-T024)
- All entity creation tasks (T025-T027) can run parallel
- Database migration (T006-T009) sequential, but can parallel with others once tables created

**Within Each User Story** (parallelizable tasks marked with [P]):
- US2: T032-T033 (idempotency checks) parallel
- US1: T062-T066 (WebSocket) can develop parallel to T067-T070 (Redis Pub/Sub setup)
- US4: T079 (entities) parallel to T080-T083 (endpoints)
- US6: All metric instrumentation (T102-T105) can run parallel

---

## Parallel Example: Foundational Phase

```bash
# After database migration (T006-T009) completes, launch in parallel:

# Security Group (Developer A)
Task T013: Implement JWT token generation
Task T014: Create OAuth 2.0 middleware
Task T015: Setup TLS 1.3
Task T016: Implement rate limiting
Task T017: Create audit logging

# Observability Group (Developer B)
Task T018: Setup Prometheus exporters
Task T019: Implement OpenTelemetry tracing
Task T020: Configure structured logging
Task T021: Create health check endpoints
Task T022-T024: Setup monitoring stack

# Core Domain Group (Developer C)
Task T025: Extend Message entity with outbox
Task T026: Create OutboxEvent entity
Task T027: Create AccessToken/RefreshToken entities
```

---

## Parallel Example: After Foundational Phase

```bash
# Once Phase 2 completes, four teams can work in parallel:

# Team A: US2 - Resilient Processing (P1)
Task T028-T043: Transactional Outbox, Idempotency, DLQ, Ordering

# Team B: US3 - Zero-Downtime (P2)
Task T044-T061: PostgreSQL HA, Kafka cluster, Kubernetes, Circuit breakers

# Team C: US6 - Observability (P3)
Task T102-T119: Prometheus, Jaeger, Loki, Grafana, Alerting

# Team D: Epic 0 - Authentication (Foundation)
Task T120-T126: OAuth 2.0 endpoints, JWT generation, token validation

# After Team A completes US2:

# Team A pivots to: US1 - Real-Time (P1, depends on US2)
Task T062-T078: WebSocket, Redis Pub/Sub, Event Broadcasting

# Team E (new): US4 - File Upload (P2, independent)
Task T079-T095: Chunked uploads, Merge worker, Resumability, GC
```

---

## Implementation Strategy

### MVP First (US2 + US1 + Authentication)

1. **Complete Phase 1**: Setup (5 tasks, ~2 hours)
2. **Complete Phase 2**: Foundational (22 tasks, ~40 hours with parallelization)
3. **Complete Phase 3**: US2 - Resilient Processing (16 tasks, ~32 hours)
4. **Complete Phase 9**: Authentication (7 tasks, ~14 hours)
5. **Complete Phase 5**: US1 - Real-Time (17 tasks, ~34 hours)
6. **STOP and VALIDATE**: Test end-to-end user journey (send message → receive real-time notification with authentication)
7. **Deploy/Demo**: MVP ready (~120 hours total, 3 weeks with 2 developers)

**MVP Delivers**: Authenticated API, real-time messaging with guaranteed delivery, resilient outbox pattern, observability basics

### Incremental Delivery (Production-Ready Platform)

1. **Sprint 1-2**: Foundational + US2 (Resilient Processing) → Reliable API with Transactional Outbox ✅
2. **Sprint 3**: US1 (Real-Time) + Authentication → Real-time messaging platform ✅
3. **Sprint 4**: US3 (Zero-Downtime) → High-availability infrastructure ✅
4. **Sprint 5**: US4 (File Upload) → File sharing capability ✅
5. **Sprint 6**: US5 (Conversation Discovery) + US6 (Observability) → Full-featured platform ✅
6. **Sprint 7**: Performance Validation + Polish → Production-ready ✅

**Total Effort**: ~320 hours (~8 weeks with 2 developers, ~4 weeks with 4 developers)

### Parallel Team Strategy (4 Developers)

**Week 1-2**: Foundation (all hands)
- Developer A: Database + Kafka setup (T006-T012)
- Developer B: Security + Auth middleware (T013-T017)
- Developer C: Observability setup (T018-T024)
- Developer D: Core entities (T025-T027)

**Week 3-4**: Parallel User Stories
- Developer A: US2 - Resilient Processing (T028-T043)
- Developer B: US3 - Zero-Downtime (T044-T061)
- Developer C: US6 - Observability (T102-T119)
- Developer D: Authentication (T120-T126)

**Week 5-6**: Parallel User Stories
- Developer A: US1 - Real-Time (T062-T078, after US2 done)
- Developer B: US4 - File Upload (T079-T095)
- Developer C/D: US5 - Conversation Discovery (T096-T101, after US1 done)

**Week 7-8**: Validation + Polish
- All developers: Performance testing (T127-T131)
- All developers: Documentation + Final report (T132-T137)
- All developers: Polish (T138-T144)

---

## Notes

- **[P] tasks**: Different files or independent components, no dependencies on incomplete tasks
- **[Story] labels**: Map tasks to user stories for traceability (US1-US6)
- **Foundational phase (Phase 2)** is the critical blocker - MUST complete before any user story work begins
- **US2 (Resilient Processing)** is the foundation for US1 (Real-Time) - Outbox pattern needed for event publishing
- **US1 (Real-Time)** is the foundation for US5 (Conversation Discovery) - WebSocket integration for read receipts
- **US3, US4, US6** are independent and can run in parallel after Foundational phase
- Each checkpoint represents a fully functional, independently testable increment
- Verify acceptance criteria at each task group before moving to next user story
- Commit after each task or logical group for easy rollback
- Total task count: **144 tasks** organized across **11 phases**
- Critical path for MVP: **T001-T005 → T006-T027 → T028-T043 → T120-T126 → T062-T078** (~120 hours)
- Full production-ready platform: **All 144 tasks** (~320 hours with parallelization)
