# Tasks: Chat4All API Hub

**Branch**: `001-chat-api-hub` | **Feature**: Chat4All API Hub  
**Input**: Design documents from `specs/001-chat-api-hub/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/api-endpoints.md ✅

**Tests**: Tests are REQUIRED per constitution (Principle III: Test-Driven Development is NON-NEGOTIABLE). Integration tests MUST be written FIRST, MUST FAIL before implementation, following TDD workflow.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `- [ ] [ID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

Single project structure (backend API with workers):
- Project root: `chat-for-all/`
- API code: `api/`, `core/`, `db/`, `services/`
- Workers: `workers/`
- Tests: `tests/`

---

## Phase 1: Setup (Shared Infrastructure) ✅

**Purpose**: Project initialization and basic structure

- [X] T001 Create project directory structure per plan.md (api/, core/, db/, services/, workers/, tests/)
- [X] T002 Create requirements.txt with dependencies (FastAPI 0.104.1, SQLAlchemy 2.0.23, kafka-python 2.0.2, minio 7.2.0, psycopg2-binary 2.9.9, bcrypt 4.1.1, pydantic 2.5.2, uvicorn 0.24.0, pytest 7.4.3, pytest-asyncio 0.21.1, httpx 0.25.1)
- [X] T003 [P] Create .env.example file with configuration template (database_url, kafka_bootstrap_servers, minio_endpoint, minio_access_key, minio_secret_key, minio_bucket, bcrypt_rounds, token_expiry_hours)
- [X] T004 [P] Create .gitignore file (venv/, __pycache__/, .env, *.pyc, .pytest_cache/, minio-data/)
- [X] T005 [P] Create README.md with project overview and quick reference to specs/001-chat-api-hub/quickstart.md

---

## Phase 2: Foundational (Blocking Prerequisites) ✅

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T006 Create core/config.py with pydantic Settings class loading from environment variables
- [X] T007 [P] Create core/__init__.py (empty or with package exports)
- [X] T008 Create core/security.py with bcrypt password hashing functions (hash_password, verify_password)
- [X] T009 Create db/__init__.py (empty or with package exports)
- [X] T010 Create db/database.py with SQLAlchemy engine, SessionLocal, and Base class
- [X] T011 Create db/models.py with all 8 ORM models: User, Conversation, ConversationMember, Message, MessageStatusHistory, FileMetadata, FileChunk, AuthSession (include ENUM types: ConversationType, MessageStatus, FileStatus)
- [X] T012 Create db/repository.py with base Repository class and methods: create_user, get_user_by_username, create_conversation, add_conversation_member, create_message, get_conversation_messages, update_message_status, create_auth_session, get_auth_session_by_token, create_file_metadata, update_file_metadata
- [X] T013 Create database initialization script in db/database.py with init() function to create all tables
- [X] T014 Create database seed script in db/database.py with seed() function to create 5 test users (user1-user5, password: password123)
- [X] T015 Create services/__init__.py (empty or with package exports)
- [X] T016 Create services/kafka_producer.py with KafkaProducerClient class and publish_message method (connects to Kafka, publishes JSON messages to specified topic)
- [X] T017 Create services/minio_client.py with MinIOClient class: methods for presigned_put_url, presigned_get_url, stat_object, remove_object
- [X] T018 Create api/__init__.py (empty or with package exports)
- [X] T019 Create api/dependencies.py with dependency injection functions: get_db (yields database session), get_current_user (validates token and returns User)
- [X] T020 Create api/schemas.py with Pydantic models for all request/response schemas: TokenRequest, TokenResponse, ConversationCreate, ConversationResponse, MessageCreate, MessageResponse, FileInitiateRequest, FileInitiateResponse, FileCompleteRequest, FileCompleteResponse, MessageListResponse
- [X] T021 Create main.py with FastAPI application initialization, CORS middleware, and health check endpoint (GET /)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Simple Text Messaging (Priority: P1) 🎯 MVP

**Goal**: Users can authenticate, create private conversations, send text messages, and verify delivery through async processing

**Independent Test**: Authenticate user → create private conversation → send text message → verify status "accepted" → worker processes message → verify status "delivered"

### Integration Tests for User Story 1 (TDD - WRITE FIRST) ✅

> **⚠️ CRITICAL**: Write these tests FIRST, ensure they FAIL before implementation

- [X] T022 [P] [US1] Create tests/__init__.py and tests/conftest.py with pytest fixtures: test_db (creates/destroys test database), test_client (TestClient with FastAPI app), mock_kafka_producer, seed_test_users
- [X] T023 [US1] Write integration test test_authentication_flow in tests/test_api.py: test POST /auth/token with valid credentials returns token, test invalid credentials returns 401
- [X] T024 [US1] Write integration test test_create_private_conversation in tests/test_api.py: test authenticated user can create private conversation with 2 members, test validation enforces exactly 2 members
- [X] T025 [US1] Write integration test test_send_text_message in tests/test_api.py: test authenticated user can send text message to conversation, test API returns status "accepted" with message_id, test unauthenticated request returns 401, test non-member cannot send to conversation (403)
- [X] T026 [US1] Write integration test test_get_conversation_messages in tests/test_api.py: test authenticated user can retrieve messages from conversation, test messages include sender, payload, status, timestamp
- [X] T027 [US1] Write unit test test_message_router_text_routing in tests/test_workers.py: test router publishes text messages to correct channel topics based on channels array

**Checkpoint**: Run tests → All tests MUST FAIL (no implementation yet)

### Implementation for User Story 1 ✅

- [X] T028 [US1] Implement POST /auth/token endpoint in api/endpoints.py: validate credentials with bcrypt, create AuthSession, return token and expiry
- [X] T029 [US1] Implement POST /v1/conversations endpoint in api/endpoints.py: validate conversation type and member count, create Conversation and ConversationMember records, return conversation details
- [X] T030 [US1] Implement POST /v1/messages endpoint in api/endpoints.py: validate message payload, check user is conversation member, create Message with status="accepted", publish to Kafka topic "message_processing" via BackgroundTasks, return {"status": "accepted", "message_id": uuid}
- [X] T031 [US1] Implement GET /v1/conversations/{conversation_id}/messages endpoint in api/endpoints.py: validate user is conversation member, retrieve messages from repository, return paginated message list with limit/offset
- [X] T032 [US1] Register all endpoints in main.py using APIRouter and include_router
- [X] T033 [US1] Create workers/__init__.py (empty or with package exports)
- [X] T034 [US1] Implement workers/message_router.py: consume from "message_processing" topic, parse message channels array, publish to "whatsapp_outgoing" if channels includes "whatsapp" or "all", publish to "instagram_outgoing" if channels includes "instagram" or "all", handle signal for graceful shutdown
- [X] T035 [US1] Implement workers/whatsapp_mock.py: consume from "whatsapp_outgoing" topic, log "INFO: Mensagem <uuid> enviada para o usuário <user_id> no WhatsApp", update message status to "delivered" in database via repository
- [X] T036 [US1] Implement workers/instagram_mock.py: consume from "instagram_outgoing" topic, log "INFO: Mensagem <uuid> enviada para o usuário <user_id> no Instagram", update message status to "delivered" in database via repository
- [X] T037 [US1] Add error handling in api/endpoints.py: 401 for invalid auth, 403 for access denied, 404 for not found, 400 for validation errors, 503 for Kafka unavailable
- [X] T038 [US1] Add logging configuration in core/config.py: structured logging for API requests and worker processing

**Checkpoint**: Run tests → All User Story 1 tests should PASS. Test end-to-end flow manually following quickstart.md validation steps.

---

## Phase 4: User Story 2 - Group Conversations (Priority: P2) ✅

**Goal**: Users can create group conversations (3-100 members) and all members can send/receive messages

**Independent Test**: Authenticate → create group conversation with 3+ members → any member sends message → all members retrieve message

### Integration Tests for User Story 2 (TDD - WRITE FIRST) ✅

- [X] T039 [P] [US2] Write integration test test_create_group_conversation in tests/test_api.py: test group creation with 3+ members, test validation enforces minimum 3 members, test validation enforces maximum 100 members, test all members can retrieve messages
- [X] T040 [US2] Write integration test test_group_message_visibility in tests/test_api.py: test message sent by one member visible to all members, test non-member cannot access group messages (403)

**Checkpoint**: Run tests → Tests MUST FAIL

### Implementation for User Story 2 ✅

- [X] T041 [US2] Extend POST /v1/conversations endpoint in api/endpoints.py: add group conversation validation (3-100 members), handle group metadata (name, description)
- [X] T042 [US2] Add group conversation member validation in api/endpoints.py for POST /v1/messages: verify user is member of group conversation before allowing message send
- [X] T043 [US2] Update GET /v1/conversations/{conversation_id}/messages in api/endpoints.py: ensure group messages include clear sender identification for all members

**Checkpoint**: Run tests → All User Story 2 tests should PASS. Group conversations fully functional.

---

## Phase 5: User Story 3 - File Upload and Sharing (Priority: P3) ✅

**Goal**: Users can upload large files (up to 2GB) using chunked upload, send file messages, and retrieve file references

**Independent Test**: Authenticate → initiate file upload → upload chunks → complete upload → send file message → retrieve message with file reference

### Integration Tests for User Story 3 (TDD - WRITE FIRST) ✅

- [X] T044 [P] [US3] Write integration test test_file_upload_initiate in tests/test_api.py: test POST /v1/files/initiate returns file_id and presigned URL, test file size validation rejects files > 2GB (413 error)
- [X] T045 [P] [US3] Write integration test test_file_upload_complete in tests/test_api.py: test POST /v1/files/complete with valid checksum marks file as completed, test invalid checksum returns 400 error
- [X] T046 [US3] Write integration test test_send_file_message in tests/test_api.py: test user can send message with payload type="file" and valid file_id, test message with invalid file_id returns 400 error
- [X] T047 [US3] Write unit test test_message_router_file_validation in tests/test_workers.py: test router verifies file exists before routing file messages, test router marks message as FAILED if file_id invalid

**Checkpoint**: Run tests → Tests MUST FAIL

### Implementation for User Story 3 ✅

- [X] T048 [P] [US3] Implement POST /v1/files/initiate endpoint in api/endpoints.py: validate file size <= 2GB, create FileMetadata record with status="uploading", generate presigned PUT URL via MinIOClient, return file_id and upload_url
- [X] T049 [P] [US3] Implement PATCH /v1/files/upload endpoint in api/endpoints.py: accept file_id and chunk_id, create FileChunk record, return next_upload_url for subsequent chunk
- [X] T050 [US3] Implement POST /v1/files/complete endpoint in api/endpoints.py: validate file exists in MinIO, calculate and verify checksum, update FileMetadata status to "completed", return file details
- [X] T051 [US3] Extend POST /v1/messages validation in api/endpoints.py: if payload type="file", verify file_id exists and status="completed" before accepting message
- [X] T052 [US3] Extend workers/message_router.py: for file messages, verify file exists in MinIO before routing to channel topics, mark message as FAILED if file missing
- [X] T053 [US3] Update GET /v1/conversations/{conversation_id}/messages in api/endpoints.py: for file messages, include filename and file_id in response

**Checkpoint**: Run tests → All User Story 3 tests should PASS. File upload and sharing fully functional.

---

## Phase 6: User Story 4 - Multi-Channel Message Routing (Priority: P4)

**Goal**: Demonstrate multi-channel routing architecture with mock connectors logging deliveries

**Independent Test**: Send message with specific channels → inspect worker logs → verify correct mock connectors processed message

### Integration Tests for User Story 4 (TDD - WRITE FIRST)

- [X] T054 [P] [US4] Write integration test test_single_channel_routing in tests/test_api.py: test message with channels=["whatsapp"] routes only to WhatsApp mock, verify via log inspection or database query
- [X] T055 [P] [US4] Write integration test test_multi_channel_routing in tests/test_api.py: test message with channels=["whatsapp", "instagram"] routes to both mocks
- [X] T056 [US4] Write integration test test_all_channels_routing in tests/test_api.py: test message with channels=["all"] routes to all available mock connectors

**Checkpoint**: Run tests → Tests MUST FAIL

### Implementation for User Story 4

- [X] T057 [US4] Verify workers/message_router.py correctly parses channels array: implement "all" keyword to route to all topics, implement specific channel routing for "whatsapp" and "instagram"
- [X] T058 [US4] Enhance workers/whatsapp_mock.py logging: ensure log format matches specification "INFO: Mensagem <uuid> enviada para o usuário <user_id> no WhatsApp"
- [X] T059 [US4] Enhance workers/instagram_mock.py logging: ensure log format matches specification "INFO: Mensagem <uuid> enviada para o usuário <user_id> no Instagram"
- [X] T060 [US4] Add MessageStatusHistory tracking in workers: create status history records when mock connectors update message status to "delivered"

**Checkpoint**: Run tests → All User Story 4 tests should PASS. Multi-channel routing fully functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T061 [P] Add comprehensive docstrings to all API endpoints in api/endpoints.py: include parameter descriptions, response models, example requests for Swagger documentation
- [X] T062 [P] Add comprehensive docstrings to all Pydantic schemas in api/schemas.py: include field descriptions, examples, constraints
- [X] T063 [P] Create unit tests in tests/test_models.py: test User model password hashing, test Conversation validation logic, test Message ENUM types
- [X] T064 [P] Add idempotency handling in api/endpoints.py POST /v1/messages: check if message_id already exists, return existing response if duplicate
- [X] T065 [P] Add request ID tracking in main.py: middleware to generate unique request_id for each API call, include in logs
- [X] T066 Add edge case handling in api/endpoints.py: implement all edge cases from spec.md (invalid auth, missing conversation, unauthorized access, duplicate message_id, oversized file, invalid file_id, Kafka unavailable, missing required fields, group member limit)
- [X] T067 [P] Create database migration scripts: Alembic or custom migration for initial schema (001_initial_schema.sql) and seed data (002_seed_users.sql)
- [X] T068 [P] Update README.md with architecture diagram, API endpoint summary, worker process descriptions
- [X] T069 [P] Verify all environment variables documented in .env.example match core/config.py Settings class
- [X] T070 Run full test suite with pytest: execute pytest -v tests/ and verify all tests pass
- [X] T071 Manual validation following specs/001-chat-api-hub/quickstart.md: complete all verification steps in quickstart guide
- [X] T072 Performance testing: verify API endpoints meet <500ms p95 latency requirement (SC-001), verify worker processing meets 5-second delivery requirement (SC-002)
- [X] T073 [P] Code quality check: run linter (flake8 or ruff) to ensure PEP 8 compliance per constitution
- [X] T074 [P] Type checking: run mypy to verify all functions have type hints per constitution
- [X] T075 Generate OpenAPI documentation: verify FastAPI auto-generates complete docs at /docs and /redoc with all endpoints, schemas, examples

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion - MVP delivered upon completion
- **User Story 2 (Phase 4)**: Depends on Foundational phase completion - Can proceed in parallel with US1 if staffed
- **User Story 3 (Phase 5)**: Depends on Foundational phase completion - Can proceed in parallel with US1/US2 if staffed
- **User Story 4 (Phase 6)**: Depends on Foundational phase completion and workers/message_router.py from US1 - Must complete after US1 T034
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies on other stories - MVP baseline
- **User Story 2 (P2)**: No dependencies on other stories - Independently testable, extends conversation creation
- **User Story 3 (P3)**: No dependencies on other stories - Independently testable, extends message types
- **User Story 4 (P4)**: Depends on message_router from US1 (T034) - Extends routing logic

### Within Each User Story

**TDD Workflow (CRITICAL)**:
1. Write integration tests FIRST (tests marked with "TDD - WRITE FIRST")
2. Run tests → verify they FAIL (no implementation)
3. Implement tasks in order
4. Run tests after each implementation task
5. Tests turn GREEN as implementation progresses
6. Mark user story complete when all tests pass

**Implementation Order**:
- Tests before implementation (TDD)
- Models/entities before services
- Services before endpoints
- Core implementation before edge cases
- Story complete before moving to next priority

### Parallel Opportunities

**Setup Phase (Phase 1)**:
- T003, T004, T005 can run in parallel (independent files)

**Foundational Phase (Phase 2)**:
- T007, T009, T015, T018 can run in parallel (__init__.py files)
- After T010 completes: T011, T012, T013, T014 can proceed in parallel

**User Story 1 Tests**:
- T022, T023, T024, T025, T026, T027 can be written in parallel (different test functions)

**User Story 1 Implementation**:
- T034, T035, T036 can be implemented in parallel (independent workers)

**User Story 2 Tests**:
- T039, T040 can be written in parallel

**User Story 3 Tests**:
- T044, T045, T046, T047 can be written in parallel

**User Story 3 Implementation**:
- T048, T049 can be implemented in parallel (different endpoints)

**User Story 4 Tests**:
- T054, T055, T056 can be written in parallel

**Polish Phase**:
- T061, T062, T063, T064, T065, T067, T068, T069, T073, T074 can run in parallel (independent improvements)

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together (TDD phase):
Task T022: Create test fixtures
Task T023: Write authentication test
Task T024: Write conversation creation test
Task T025: Write message sending test
Task T026: Write message retrieval test
Task T027: Write router unit test

# After tests written and failing, launch parallel implementation:
Task T034: Implement message router worker
Task T035: Implement WhatsApp mock worker
Task T036: Implement Instagram mock worker
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T021) - CRITICAL blocking phase
3. Complete Phase 3: User Story 1 (T022-T038)
4. **STOP and VALIDATE**: Run all User Story 1 tests, verify end-to-end flow
5. Deploy/demo MVP ✅

**Estimated effort**: ~40 hours for MVP (US1 only)

### Incremental Delivery

1. Setup + Foundational → Foundation ready (~20 hours)
2. Add User Story 1 → Test independently → Deploy/Demo MVP (~20 hours)
3. Add User Story 2 → Test independently → Deploy/Demo (~8 hours)
4. Add User Story 3 → Test independently → Deploy/Demo (~16 hours)
5. Add User Story 4 → Test independently → Deploy/Demo (~8 hours)
6. Polish → Final delivery (~8 hours)

**Total estimated effort**: ~80 hours for complete system

### Parallel Team Strategy

With 3 developers:

1. **Week 1**: All developers complete Setup + Foundational together (~20 hours)
2. **Week 2**: Once Foundational is done:
   - Developer A: User Story 1 (T022-T038)
   - Developer B: User Story 2 (T039-T043)
   - Developer C: User Story 3 (T044-T053)
3. **Week 3**: 
   - All: User Story 4 together (depends on US1 router)
   - All: Polish phase
4. Stories complete and integrate independently

**Timeline with 3 developers**: ~2-3 weeks

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- **TDD is NON-NEGOTIABLE**: Tests written FIRST, fail, then implement, tests pass
- Verify tests fail before implementing (Red-Green-Refactor cycle)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence

---

## Task Count Summary

**Total Tasks**: 75

**By Phase**:
- Phase 1 (Setup): 5 tasks
- Phase 2 (Foundational): 16 tasks
- Phase 3 (User Story 1): 17 tasks (6 tests + 11 implementation)
- Phase 4 (User Story 2): 5 tasks (2 tests + 3 implementation)
- Phase 5 (User Story 3): 10 tasks (4 tests + 6 implementation)
- Phase 6 (User Story 4): 7 tasks (3 tests + 4 implementation)
- Phase 7 (Polish): 15 tasks

**Test Tasks**: 15 integration/unit tests (20% of total)
**Implementation Tasks**: 60 (80% of total)

**Parallel Opportunities**: 25+ tasks marked [P]

**Critical Path**: Setup → Foundational → User Story 1 → Validate MVP (38 tasks for MVP)
