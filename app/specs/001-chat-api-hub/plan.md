# Implementation Plan: Chat4All API Hub

**Branch**: `001-chat-api-hub` | **Date**: 2025-11-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/001-chat-api-hub/spec.md`

**Note**: This plan implements a distributed messaging API hub for academic demonstration of asynchronous communication, message routing, and file storage patterns.

## Summary

The Chat4All API Hub is an academic proof-of-concept implementing a ubiquitous communication platform. The system enables users to exchange text messages and files (up to 2GB) through a REST API, with asynchronous message processing via Kafka workers and multi-channel routing through mock connectors (WhatsApp, Instagram). Key technical patterns include: async request handling with immediate response, event-driven message routing, chunked file upload with integrity verification, and separation of concerns across API/workers/storage layers.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI 0.104+, SQLAlchemy 2.0+, kafka-python 2.0+ or confluent-kafka 2.3+, minio 7.2+, psycopg2-binary 2.9+, bcrypt 4.1+, pydantic 2.5+, uvicorn 0.24+  
**Storage**: PostgreSQL 15+ (relational data), MinIO (S3-compatible object storage for files)  
**Testing**: pytest 7.4+, pytest-asyncio for async tests, httpx for API client tests  
**Target Platform**: Linux/Windows/macOS local development environment (no Docker initially)  
**Project Type**: Backend API service with separate worker processes (single repository, multiple entry points)  
**Performance Goals**: 500ms p95 latency for message acceptance, 5-second message delivery (API → worker → delivery), support 50 concurrent users  
**Constraints**: <500ms API response time (message acceptance only, not delivery), files up to 2GB, local development without container orchestration, no production cloud deployment  
**Scale/Scope**: Academic POC supporting 4 user stories, 6 API endpoints, 3 background workers, ~2000 lines of Python code estimated

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Status**: ✅ **COMPLIANT** - All constitution principles satisfied

### Principle I: Code Quality & Clarity ✅
- Python 3.11+ specified
- PEP 8 compliance required
- Type hints mandatory on all functions
- Clean architecture with clear layer separation (api/, workers/, db/, services/)
- Single Responsibility Principle enforced through modular structure

### Principle II: Modular Architecture ✅
- API layer: `api/` directory with endpoints and schemas
- Business logic: `workers/` directory for Kafka consumers and processors
- Data access: `db/` directory with models and repositories
- Each layer independently testable via pytest

### Principle III: Test-Driven Development ✅
- pytest framework specified
- Integration tests required for all API endpoints (`tests/test_api.py`)
- Unit tests for critical worker logic
- TDD workflow: write tests → fail → implement → pass

### Principle IV: Technology Stack Compliance ✅
- FastAPI for REST API with auto-generated OpenAPI docs
- PostgreSQL with SQLAlchemy ORM
- Apache Kafka for message broker
- MinIO for S3-compatible object storage
- pytest for testing framework
- bcrypt for password hashing
- No deviations from mandated stack

### Principle V: Documentation-First Approach ✅
- FastAPI generates automatic Swagger/OpenAPI documentation
- README.md will contain step-by-step local setup instructions
- No Docker dependency for initial development
- Configuration explicitly documented

### Principle VI: MVP-Focused Simplicity ✅
- Scope limited to 4 user stories from spec
- Simple username/password authentication (no JWT/OAuth complexity)
- Mock connectors only (no real WhatsApp/Instagram API integration)
- No cloud deployment, auto-scaling, or production infrastructure
- Focus on distributed systems learning objectives

**Complexity Justification**: None required - plan fully adheres to constitution

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
chat-for-all/
├── main.py                    # FastAPI application entry point (uvicorn server)
├── requirements.txt           # Python dependencies
├── .env.example              # Environment variables template
├── README.md                  # Setup and execution instructions
│
├── api/                       # API Layer (FastAPI endpoints)
│   ├── __init__.py
│   ├── endpoints.py          # REST endpoints (auth, conversations, messages, files)
│   ├── schemas.py            # Pydantic request/response models
│   └── dependencies.py       # Dependency injection (auth, db sessions)
│
├── core/                      # Core Configuration
│   ├── __init__.py
│   ├── config.py             # Settings (database, kafka, minio URLs, secrets)
│   └── security.py           # Authentication logic (bcrypt, token generation)
│
├── db/                        # Data Access Layer
│   ├── __init__.py
│   ├── database.py           # SQLAlchemy engine and session management
│   ├── models.py             # ORM models (User, Conversation, Message, FileMetadata)
│   └── repository.py         # Data access methods (CRUD operations)
│
├── services/                  # External Service Clients
│   ├── __init__.py
│   ├── kafka_producer.py     # Kafka message publishing
│   └── minio_client.py       # MinIO file operations (presigned URLs, validation)
│
├── workers/                   # Background Workers (Kafka consumers)
│   ├── __init__.py
│   ├── message_router.py     # Routes messages from main topic to channel topics
│   ├── whatsapp_mock.py      # WhatsApp mock connector (logs + status update)
│   └── instagram_mock.py     # Instagram mock connector (logs + status update)
│
├── tests/                     # Test Suite
│   ├── __init__.py
│   ├── conftest.py           # Pytest fixtures (test db, test client, mock services)
│   ├── test_api.py           # Integration tests for API endpoints
│   ├── test_workers.py       # Unit tests for worker logic
│   └── test_models.py        # Unit tests for data models
│
└── specs/                     # Feature specifications (this directory)
    └── 001-chat-api-hub/
        ├── spec.md
        ├── plan.md           # This file
        ├── research.md       # (Generated in Phase 0)
        ├── data-model.md     # (Generated in Phase 1)
        ├── quickstart.md     # (Generated in Phase 1)
        └── contracts/        # (Generated in Phase 1)
```

**Structure Decision**: Single project (Option 1) selected. This is a backend API service with multiple worker processes, all part of a single Python codebase. The structure follows clean architecture with clear separation:
- **api/**: HTTP layer (FastAPI routers, schemas, auth dependencies)
- **core/**: Application configuration and cross-cutting concerns
- **db/**: Data persistence layer (SQLAlchemy models and repository pattern)
- **services/**: Integration with external systems (Kafka, MinIO)
- **workers/**: Asynchronous background processing (Kafka consumers)
- **tests/**: Test suite organized by test type (integration, unit)

Each directory is independently testable. Workers run as separate Python processes (`python -m workers.message_router`) but share the same codebase.
