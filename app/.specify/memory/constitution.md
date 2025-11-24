<!--
SYNC IMPACT REPORT
==================
Version Change: N/A → 1.0.0
Change Type: Initial ratification (MAJOR)
Modified Principles: N/A (new document)
Added Sections:
  - Core Principles (6 principles)
  - Technology Stack
  - Development Workflow
  - Governance
Removed Sections: N/A
Templates Requiring Updates:
  ✅ plan-template.md - Constitution Check section references this document
  ✅ spec-template.md - Requirements align with principles
  ✅ tasks-template.md - Test-driven and modular approach reflected
Follow-up TODOs: None
-->

# Chat4All Constitution

## Core Principles

### I. Code Quality & Clarity (NON-NEGOTIABLE)

All code MUST be written in Python 3.11+ and strictly follow PEP 8 standards. Every function and method MUST include type hints to ensure type safety and clarity. Code MUST be organized using clean architecture principles with clear separation between API layer (FastAPI), business logic (workers), and data access (repositories). Functions MUST remain small and follow the Single Responsibility Principle.

**Rationale**: Clear, typed code reduces bugs, improves maintainability, and enables effective collaboration in distributed system development. Type hints catch errors at development time rather than runtime.

### II. Modular Architecture

The system MUST maintain strict separation of concerns across three distinct layers: API endpoints (FastAPI), business logic workers (Kafka consumers/processors), and data repositories (SQLAlchemy ORM). Each layer MUST be independently testable and loosely coupled through well-defined interfaces.

**Rationale**: Modular architecture enables independent scaling, testing, and development of each component. This is critical for a distributed communication system where different concerns (HTTP API, async processing, data persistence) have different requirements.

### III. Test-Driven Development (NON-NEGOTIABLE)

Every new API endpoint MUST have integration tests validating the complete request-response flow. Critical business logic in workers MUST have unit test coverage. All tests MUST use pytest. Tests MUST be written before implementation and MUST fail before code is written.

**Rationale**: Tests ensure system reliability and provide living documentation. For an academic proof-of-concept, demonstrable test coverage validates technical rigor.

### IV. Technology Stack Compliance

The project MUST use the following technology stack without deviation:
- **API Framework**: FastAPI for REST endpoints with automatic OpenAPI documentation
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Message Broker**: Apache Kafka for asynchronous communication
- **Object Storage**: MinIO (S3-compatible) for large file storage
- **Testing**: pytest framework

**Rationale**: This stack balances modern best practices with academic learning objectives. Each component addresses specific distributed system concerns (async processing, persistence, file storage) while remaining feasible for local development.

### V. Documentation-First Approach

API documentation MUST be automatically generated via FastAPI/Swagger with clear descriptions and examples for all endpoints. The README.md MUST contain complete, step-by-step instructions for local setup without Docker. All configuration requirements MUST be explicitly documented.

**Rationale**: Clear documentation is essential for academic projects and enables independent evaluation. Auto-generated API docs ensure documentation stays synchronized with implementation.

### VI. MVP-Focused Simplicity (NON-NEGOTIABLE)

Development MUST focus exclusively on requirements defined for the academic proof-of-concept. The system MUST NOT include cloud deployment configurations, auto-scaling infrastructure, JWT-based authentication, or production-grade connector implementations beyond what is explicitly required. Simple username/password authentication with bcrypt hashing is sufficient.

**Rationale**: Academic deadlines and learning objectives require focused scope. Over-engineering reduces time for core distributed systems concepts (message queues, async processing, data consistency) which are the true learning targets.

## Technology Stack

**Language**: Python 3.11+

**Core Dependencies**:
- FastAPI (API framework with OpenAPI generation)
- SQLAlchemy (ORM for PostgreSQL)
- kafka-python or confluent-kafka (Kafka client)
- minio (S3-compatible object storage client)
- bcrypt (password hashing)
- pytest (testing framework)

**Infrastructure** (local development):
- PostgreSQL database
- Apache Kafka broker
- MinIO server
- No Docker orchestration required for initial development

**Code Style**: PEP 8 enforced via linters (flake8 or ruff)

## Development Workflow

### Code Structure

Project MUST follow clean architecture with this structure:

```
src/
├── api/          # FastAPI endpoints, routers, request/response models
├── workers/      # Kafka consumers, message processors
├── models/       # SQLAlchemy ORM models
├── repositories/ # Data access layer
├── services/     # Business logic
└── config/       # Configuration management

tests/
├── integration/  # API integration tests
└── unit/         # Business logic unit tests
```

### Testing Requirements

- **Integration Tests**: MUST cover all API endpoints with full request/response validation
- **Unit Tests**: MUST cover critical business logic in workers and services
- **Test Isolation**: Tests MUST NOT depend on external services running (use mocks/fixtures)
- **Test Execution**: `pytest` MUST run all tests successfully before any PR merge

### Security Requirements

- Passwords MUST be hashed using bcrypt before storage
- Database credentials MUST be managed via environment variables
- API endpoints MUST validate input data using Pydantic models
- File uploads MUST validate file types and sizes

### Quality Gates

Before considering any feature complete:

1. All tests pass (`pytest`)
2. Code follows PEP 8 (verified via linter)
3. Type hints present on all functions
4. API documentation generated and accurate
5. README reflects any new setup requirements

## Governance

This constitution supersedes all other development practices and decisions. Any code review, feature design, or implementation choice MUST align with these principles.

**Amendment Process**:
- Amendments require documented justification
- Version must be incremented per semantic versioning
- Major version change for principle removal/redefinition
- Minor version change for new principle additions
- Patch version change for clarifications only

**Compliance**:
- All specifications and plans MUST validate against constitution principles
- Complexity that violates principles MUST be justified in planning documents
- The `/speckit.plan` command MUST include Constitution Check validation
- Templates in `.specify/templates/` MUST align with these principles

**Guidance**:
- Prompt files in `.github/prompts/` provide runtime development guidance
- Agent files in `.github/agents/` must reference this constitution for decision-making

**Version**: 1.0.0 | **Ratified**: 2025-11-24 | **Last Amended**: 2025-11-24
