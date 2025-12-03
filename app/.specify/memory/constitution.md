<!--
SYNC IMPACT REPORT
==================
Version Change: 1.0.0 → 2.0.0
Change Type: MAJOR (backward incompatible governance redefinition)
Modified Principles:
  - Principle I: "Code Quality & Clarity" → "Ubiquity and Interoperability" (complete redefinition)
  - Principle II: "Modular Architecture" → "Reliability and Resilience" (complete redefinition)
  - Principle III: "Test-Driven Development" → "Scalability and Performance" (complete redefinition)
  - Principle IV: "Technology Stack Compliance" → "Consistency and Order" (complete redefinition)
  - Principle V: "Documentation-First Approach" → "Extensibility and Maintainability" (complete redefinition)
  - Principle VI: "MVP-Focused Simplicity" → "Security and Privacy" (complete redefinition)
Added Sections:
  - Principle VII: Observability (NEW)
Removed Sections: N/A
Templates Requiring Updates:
  ⚠ plan-template.md - Constitution Check section must align with new principles
  ⚠ spec-template.md - Requirements must align with new principles (reliability, scalability)
  ⚠ tasks-template.md - Task categorization must reflect new principle-driven types (observability, fault-tolerance)
Follow-up TODOs:
  - Update all template files to reflect production-grade distributed system requirements
  - Verify all existing specs against new principles (especially reliability and scalability requirements)
  - Update README.md to reflect production-grade positioning vs MVP academic focus
-->

# Chat4All Constitution

**Project**: Chat4All v2 - Ubiquitous Communication Platform  
**Description**: High-performance, multi-channel messaging hub providing unified REST and gRPC APIs for WhatsApp, Instagram Direct, Messenger, and Telegram with guaranteed message delivery and horizontal scalability.

## Core Principles

### I. Ubiquity and Interoperability (NON-NEGOTIABLE)

The platform MUST provide a single, unified API (REST and gRPC) that abstracts ALL supported messaging channels (WhatsApp, Instagram Direct, Messenger, Telegram). The API contract MUST remain stable and channel-agnostic, exposing identical operations regardless of underlying platform. New channel connectors MUST integrate without requiring API contract changes. All message formats MUST be normalized to a canonical internal representation before routing.

**Rationale**: Breaking down communication silos is the platform's core value proposition. Users and developers MUST NOT need to understand platform-specific quirks. A stable, unified API enables rapid integration and prevents vendor lock-in.

### II. Reliability and Resilience (NON-NEGOTIABLE)

The system MUST guarantee **at-least-once message delivery** under ALL failure scenarios including network partitions, service crashes, and offline recipients. The platform MUST maintain **≥99.95% availability (SLA)** with automatic failover for all critical components (API gateways, message brokers, databases). All state-changing operations MUST be idempotent. Message persistence MUST use durable storage with replication factor ≥3. Circuit breakers MUST protect against cascading failures.

**Rationale**: Lost messages destroy user trust and business value. High availability is non-negotiable for a communication platform. At-least-once delivery with idempotency provides a pragmatic balance between reliability and complexity.

### III. Scalability and Performance (NON-NEGOTIABLE)

The architecture MUST scale horizontally to support:
- **Users**: Millions of concurrent connections
- **Throughput**: 10 million messages per minute (peak traffic)
- **Latency**: <200ms p99 for API ingestion to queue persistence

All services MUST be stateless to enable automatic scaling. Message processing MUST use partitioned queues (Kafka topics with 100+ partitions). Database queries MUST be optimized for <50ms p95 latency. The system MUST support load shedding and graceful degradation under extreme load.

**Rationale**: Communication platforms face unpredictable traffic spikes. Horizontal scalability is the only viable approach to handle millions of users. Performance requirements ensure acceptable user experience even under load.

### IV. Consistency and Order (NON-NEGOTIABLE)

The system MUST preserve **causal ordering** of messages within a single conversation. Messages from the same sender in the same conversation MUST be delivered in send order. The platform MUST provide **strong eventual consistency** across replicas with conflict-free resolution. Duplicate message detection MUST be implemented using idempotency keys (message_id) with deduplication windows ≥24 hours. The system MUST guarantee exactly-once semantics from the user perspective (at-least-once delivery + idempotent processing).

**Rationale**: Out-of-order messages break conversation context and user experience. Strong eventual consistency with causal ordering provides the right balance for distributed messaging. Deduplication simulates exactly-once delivery without requiring distributed transactions.

### V. Extensibility and Maintainability (NON-NEGOTIABLE)

The architecture MUST be modular with clear separation between:
- **Core Platform**: API gateway, message routing, persistence
- **Channel Connectors**: Platform-specific adapters (plugins)
- **Storage Layer**: Message store, user directory, file storage

New connectors MUST integrate via well-defined interfaces without modifying core services. All code MUST follow clean architecture principles with dependency inversion. Services MUST communicate via message passing (Kafka) or RPC (gRPC) with explicit contracts. Documentation MUST include architecture diagrams, API specifications (OpenAPI/Protobuf), and runbooks for all operational scenarios.

**Rationale**: A platform supporting multiple channels MUST be extensible by design. Modular architecture enables independent development, testing, and deployment of connectors. Clean separation reduces cognitive load and accelerates development.

### VI. Security and Privacy (NON-NEGOTIABLE)

All data in transit MUST be encrypted using TLS 1.3+. The API MUST enforce authentication (OAuth 2.0 or API keys) and authorization (RBAC) on ALL endpoints. Passwords MUST be hashed using bcrypt (cost factor ≥12) or Argon2. Sensitive data at rest MUST be encrypted (AES-256). The platform MUST implement:
- **Rate Limiting**: Per-user (100 req/min) and global (configurable) limits
- **Input Validation**: Pydantic models for REST, Protobuf for gRPC
- **Audit Logging**: All security events (auth failures, privilege escalations) to immutable log store

The system MUST comply with GDPR data retention and deletion requirements.

**Rationale**: Communication platforms are high-value targets for attacks. Encryption, authentication, and rate limiting are mandatory security controls. Privacy regulations (GDPR) require explicit compliance mechanisms.

### VII. Observability (NON-NEGOTIABLE)

The system MUST provide full operational transparency through:
- **Metrics**: Prometheus-compatible metrics for ALL services (request rates, error rates, latency histograms, queue depths)
- **Distributed Tracing**: OpenTelemetry tracing across ALL service boundaries with trace propagation
- **Centralized Logging**: Structured logs (JSON) aggregated in ELK/Loki with correlation IDs

All services MUST expose health check endpoints (/health, /ready). Dashboards MUST visualize key SLIs (availability, latency, error rates). Alerts MUST trigger for SLA violations. The platform MUST support chaos engineering experiments (fault injection).

**Rationale**: Complex distributed systems are opaque without instrumentation. Observability is not optional—it's the foundation for debugging, performance optimization, and reliability engineering. Proactive monitoring prevents outages.

## Technology Stack

**Language**: Python 3.11+ (primary), Go 1.21+ (performance-critical connectors optional)

**Core Dependencies**:
- **API Framework**: FastAPI (REST) + gRPC (Python gRPC libraries)
- **Message Broker**: Apache Kafka 3.5+ (guaranteed delivery, partitioning)
- **Database**: PostgreSQL 15+ with read replicas (user data, message metadata)
- **Cache**: Redis 7+ (session store, rate limiting, deduplication)
- **Object Storage**: MinIO or S3 (file attachments ≤2GB)
- **Orchestration**: Kubernetes 1.28+ (horizontal scaling, auto-failover)

**Observability Stack**:
- Prometheus + Grafana (metrics)
- Jaeger or Tempo (distributed tracing)
- ELK Stack or Loki (centralized logging)

**Security**:
- OAuth 2.0 (authentication)
- TLS 1.3 (encryption)
- bcrypt/Argon2 (password hashing)

**Code Quality**: PEP 8, mypy (type checking), black (formatting), pylint (linting)

## Development Workflow

### Code Structure

Project MUST follow hexagonal architecture:

```
platform/
├── api/
│   ├── rest/          # FastAPI endpoints
│   ├── grpc/          # gRPC services
│   └── gateway/       # API gateway (rate limiting, auth)
├── core/
│   ├── domain/        # Business entities (Message, Conversation, User)
│   ├── ports/         # Interface definitions (IMessageStore, IConnector)
│   └── usecases/      # Business logic (SendMessage, RouteMessage)
├── adapters/
│   ├── connectors/    # Channel-specific adapters (WhatsApp, Instagram, etc.)
│   ├── repositories/  # Data access (PostgreSQL, Redis)
│   └── messaging/     # Kafka producers/consumers
├── infrastructure/
│   ├── config/        # Environment configuration
│   ├── monitoring/    # Metrics, tracing, logging setup
│   └── security/      # Auth, encryption utilities
└── workers/
    ├── router/        # Message routing worker
    └── connectors/    # Connector workers (per channel)

tests/
├── unit/              # Domain logic tests
├── integration/       # API + DB tests
├── contract/          # API contract tests (OpenAPI compliance)
└── e2e/               # End-to-end message delivery tests
```

### Testing Requirements

- **Unit Tests**: MUST cover ALL domain logic (usecases) with ≥90% coverage
- **Integration Tests**: MUST validate API + database interactions
- **Contract Tests**: MUST verify API compliance with OpenAPI/Protobuf specs
- **E2E Tests**: MUST validate complete message flows (send → queue → deliver)
- **Chaos Tests**: MUST simulate failures (network partitions, service crashes)
- **Load Tests**: MUST validate performance targets (10M msg/min, <200ms latency)

### Performance Requirements

- **API Latency**: <200ms p99 (ingestion to queue)
- **Message Throughput**: 10 million messages/minute (peak)
- **Database Query Latency**: <50ms p95
- **Availability**: ≥99.95% SLA (4.38 hours downtime/year max)

### Security Requirements

- TLS 1.3 for ALL external communication
- OAuth 2.0 or API key authentication
- RBAC authorization with least-privilege principle
- Rate limiting: 100 req/min per user, configurable global limit
- Input validation via Pydantic (REST) and Protobuf (gRPC)
- Audit logging for ALL security events

### Quality Gates

Before merging ANY code:

1. All tests pass (unit, integration, contract)
2. Code coverage ≥90% for domain logic
3. Type checking passes (mypy --strict)
4. Linting passes (pylint, flake8)
5. API documentation up to date (OpenAPI/Protobuf)
6. Performance benchmarks pass (<200ms p99)
7. Security scan passes (no critical vulnerabilities)

## Governance

This constitution defines the architectural and operational standards for Chat4All v2. ALL design decisions, code reviews, and operational procedures MUST align with these principles.

**Amendment Process**:
- Amendments require architectural review and documented justification
- Version MUST be incremented per semantic versioning:
  - **MAJOR**: Backward incompatible principle changes (e.g., removing reliability guarantee)
  - **MINOR**: New principles added (e.g., adding compliance requirement)
  - **PATCH**: Clarifications, typo fixes, non-semantic updates
- Amendments MUST be approved by technical lead and product owner

**Compliance**:
- ALL feature specifications MUST validate against constitution principles
- Architecture Decision Records (ADRs) MUST reference relevant principles
- The `/speckit.plan` command MUST include Constitution Check validation
- Templates in `.specify/templates/` MUST align with these principles
- Violations MUST be explicitly justified in planning documents (Complexity Tracking table)

**Review Cadence**:
- Constitution MUST be reviewed quarterly for alignment with evolving requirements
- Post-incident reviews MUST identify constitution gaps and propose amendments
- Performance benchmarks MUST be updated as scale targets evolve

**Version**: 2.0.0 | **Ratified**: 2025-11-30 | **Last Amended**: 2025-11-30
