# Chat4All v2 - Ubiquitous Communication Platform

## 📋 Visão Geral

**Chat4All v2** is a high-performance, production-grade ubiquitous communication platform designed to act as a central hub for various messaging channels including WhatsApp, Instagram Direct, Messenger, and Telegram. It provides a unified API (REST and gRPC) that abstracts the complexity of each underlying platform, enabling users and developers to send and receive messages and files across different channels seamlessly.

### Key Capabilities

- **Multi-Channel Integration**: Unified API for WhatsApp, Instagram, Messenger, Telegram
- **High Availability**: ≥99.95% SLA with automatic failover
- **Massive Scale**: Supports millions of concurrent users and 10M messages/minute
- **Guaranteed Delivery**: At-least-once message delivery with idempotent processing
- **Low Latency**: <200ms p99 API response time
- **Full Observability**: Comprehensive metrics, tracing, and logging

## 🎯 Funcionalidades

- **Mensagens de Texto**: Conversas privadas e em grupo
- **Upload de Arquivos**: Suporte a arquivos até 2GB com upload fragmentado
- **Roteamento Multi-Canal**: Entrega assíncrona via Kafka para WhatsApp/Instagram
- **Autenticação**: Sistema simples baseado em tokens

## 🏗️ Arquitetura

### Diagrama de Componentes

```
┌─────────────────┐
│   API Clients   │
└────────┬────────┘
         │ HTTP/REST
         ↓
┌─────────────────────────────────────────────┐
│            FastAPI Application               │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │  /auth   │  │  /v1/*   │  │  /files   │ │
│  └──────────┘  └──────────┘  └───────────┘ │
└───────┬─────────────────────────────┬───────┘
        │                             │
        ↓                             ↓
┌──────────────┐              ┌──────────────┐
│  PostgreSQL  │              │    Kafka     │
│              │              │ ┌──────────┐ │
│ • users      │              │ │ message_ │ │
│ • conversations│            │ │processing│ │
│ • messages   │              │ └────┬─────┘ │
│ • files      │              └──────┼───────┘
└──────────────┘                     │
                                     ↓
                            ┌────────────────┐
                            │ Message Router │
                            │    Worker      │
                            └───┬────────┬───┘
                                │        │
                   ┌────────────┘        └────────────┐
                   ↓                                  ↓
          ┌─────────────────┐              ┌──────────────────┐
          │ WhatsApp Worker │              │ Instagram Worker │
          │ (Mock Connector)│              │  (Mock Connector)│
          └─────────────────┘              └──────────────────┘
                   │                                  │
                   └──────────────┬───────────────────┘
                                  ↓
                          ┌───────────────┐
                          │  PostgreSQL   │
                          │ (Status Update)│
                          └───────────────┘
```

### Estrutura de Diretórios

```
chat-for-all/
├── api/              # REST API Layer
│   ├── endpoints.py  # All HTTP endpoints
│   ├── schemas.py    # Pydantic request/response models
│   └── dependencies.py # Dependency injection (auth, db)
├── core/             # Core Infrastructure
│   ├── config.py     # Environment configuration
│   └── security.py   # Password hashing (bcrypt)
├── db/               # Data Access Layer
│   ├── models.py     # SQLAlchemy ORM models
│   ├── repository.py # Database operations
│   └── database.py   # DB connection and initialization
├── services/         # External Service Clients
│   ├── kafka_producer.py # Kafka message publishing
│   └── minio_client.py   # MinIO file storage
├── workers/          # Async Message Processors
│   ├── message_router.py  # Routes messages to channels
│   ├── whatsapp_mock.py   # WhatsApp connector (mock)
│   └── instagram_mock.py  # Instagram connector (mock)
├── tests/            # Test Suite
│   ├── test_api.py       # Integration tests (API)
│   ├── test_workers.py   # Unit tests (workers)
│   ├── test_models.py    # Unit tests (models)
│   └── conftest.py       # Pytest fixtures
├── migrations/       # Database Migrations
│   ├── 001_initial_schema.sql
│   └── 002_seed_users.sql
└── main.py           # Application entry point
```

### Fluxo de Mensagens

1. **Cliente** envia POST `/v1/messages` com payload (texto ou arquivo)
2. **API** valida request, cria registro no PostgreSQL com status "accepted"
3. **API** publica mensagem no Kafka topic `message_processing` (background task)
4. **Message Router Worker** consome mensagem e roteia para canais:
   - `channels: ["whatsapp"]` → `whatsapp_outgoing` topic
   - `channels: ["instagram"]` → `instagram_outgoing` topic
   - `channels: ["all"]` → ambos os topics
5. **Channel Workers** (WhatsApp/Instagram) processam e atualizam status para "delivered"
6. **Cliente** consulta GET `/v1/conversations/{id}/messages` para ver status atualizado

## 🚀 Quick Start

### Development Setup (Single-Broker)

Para desenvolvimento local com configuração simplificada:

📖 **[specs/001-chat-api-hub/quickstart.md](specs/001-chat-api-hub/quickstart.md)**

O guia completo inclui:
- Pré-requisitos (Python 3.11+, PostgreSQL, Kafka, MinIO)
- Instalação passo a passo (~30 minutos)
- Verificação de funcionamento
- Troubleshooting

### Production Setup (Kafka HA Cluster)

Para ambiente de produção com alta disponibilidade:

📖 **[docs/KAFKA_HA_GUIDE.md](docs/KAFKA_HA_GUIDE.md)**

O guia de produção inclui:
- **Kafka HA Cluster**: 3 brokers + 3 ZooKeeper nodes (zero downtime)
- **Failover Testing**: Validação de resiliência e recuperação automática
- **Health Monitoring**: Prometheus metrics e Kafka UI (http://localhost:8080)
- **Performance Tuning**: Otimizações para throughput e latência

**Quick Start (Production)**:
```bash
# 1. Iniciar Kafka HA Cluster (3 brokers)
docker-compose -f docker-compose.kafka-cluster.yml up -d

# 2. Aguardar inicialização (~60 segundos)
docker-compose -f docker-compose.kafka-cluster.yml ps

# 3. Verificar saúde do cluster
# Kafka UI: http://localhost:8080
# Health Metrics: http://localhost:9090/metrics

# 4. Iniciar aplicação (opcional - requer integração)
# docker-compose up -d postgres redis minio api workers
```

**HA Features**:
- ✅ **Zero Data Loss**: RF=3, min.insync.replicas=2, acks='all'
- ✅ **Automatic Failover**: Kill 1 broker → system continues operating
- ✅ **Health Monitoring**: Real-time metrics via Prometheus (port 9090)
- ✅ **Web Interface**: Kafka UI for cluster visualization (port 8080)

## 🧪 Desenvolvimento

```bash
# Instalar dependências
pip install -r requirements.txt

# Configurar ambiente
cp .env.example .env
# Edite .env com suas configurações

# Executar testes
pytest -v tests/

# Iniciar API
uvicorn main:app --reload

# Iniciar workers (em terminais separados)
python workers/message_router.py
python workers/whatsapp_mock.py
python workers/instagram_mock.py
```

## 📚 Documentação

### Especificações do Projeto

- **Especificação Completa**: [specs/001-chat-api-hub/spec.md](specs/001-chat-api-hub/spec.md)
- **Modelo de Dados**: [specs/001-chat-api-hub/data-model.md](specs/001-chat-api-hub/data-model.md)
- **Contratos API**: [specs/001-chat-api-hub/contracts/api-endpoints.md](specs/001-chat-api-hub/contracts/api-endpoints.md)
- **Decisões Técnicas**: [specs/001-chat-api-hub/research.md](specs/001-chat-api-hub/research.md)

### API Endpoints

#### Autenticação

- `POST /auth/token` - Autenticar usuário e obter token
  - Request: `{"username": "user1", "password": "password123"}`
  - Response: `{"token": "uuid", "expires_at": "timestamp", ...}`

#### Conversas

- `POST /v1/conversations` - Criar conversa (privada ou grupo)
  - Private: 2 membros exatos
  - Group: 3-100 membros
- `GET /v1/conversations/{id}/messages` - Listar mensagens com paginação
  - Query params: `limit` (default: 50), `offset` (default: 0)

#### Mensagens

- `POST /v1/messages` - Enviar mensagem (texto ou arquivo)
  - Suporta idempotência via `message_id`
  - Channels: `["whatsapp"]`, `["instagram"]`, ou `["all"]`
  - Status inicial: "accepted" → processamento assíncrono

#### Arquivos

- `POST /v1/files/initiate` - Iniciar upload (max 2GB)
  - Retorna `file_id` e URL presigned para upload direto ao MinIO
- `POST /v1/files/complete` - Finalizar upload
  - Valida checksum SHA-256 e marca arquivo como "completed"

### Documentação Interativa

Quando a API estiver rodando, acesse:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🧪 Load Testing

Para validação de performance e escalabilidade:

📖 **[LOAD_TESTING_SUMMARY.md](LOAD_TESTING_SUMMARY.md)**

O guia de load testing inclui:
- **API Throughput**: 166.666 req/s baseline (5000 concurrent users)
- **WebSocket Scalability**: 10.000 concurrent connections
- **File Upload**: 100 concurrent uploads (1GB files)
- **Sustained Load**: 15 minutes continuous operation

**Quick Start (Load Tests)**:
```bash
# 1. Garantir que os serviços estejam rodando (development ou production)
docker-compose ps  # OR docker-compose -f docker-compose.kafka-cluster.yml ps

# 2. Executar todos os testes (~45 minutos)
cd tests\load
.\run_all_tests.ps1
```

**⚠️ Infrastructure Note**: Load tests require API services running with **either** single-broker Kafka (dev) **or** Kafka HA cluster (prod), not both simultaneously. See [LOAD_TESTING_STATUS.md](LOAD_TESTING_STATUS.md) for deployment options.

---

## 🏭 Production Features

O sistema implementa recursos enterprise-grade para ambientes de produção:

### Reliability & Resilience
- ✅ **Transactional Outbox Pattern**: Garantia de entrega de mensagens (zero perda)
- ✅ **Circuit Breakers**: Proteção contra cascading failures
- ✅ **Rate Limiting**: Proteção contra abuso (5 req/s por usuário)
- ✅ **Health Checks**: Endpoints de saúde para Kubernetes liveness/readiness

### Real-Time Communication
- ✅ **WebSocket Support**: Notificações em tempo real (10K+ connections)
- ✅ **Redis Pub/Sub**: Distribuição de mensagens entre workers
- ✅ **Message Ordering**: Garantia de ordem via Kafka partitions

### Security & Authentication
- ✅ **OAuth 2.0**: Autenticação via Google/GitHub
- ✅ **JWT Tokens**: Autenticação stateless com refresh tokens
- ✅ **CORS Protection**: Configuração segura para cross-origin requests

### Observability
- ✅ **Prometheus Metrics**: Application e Kafka HA health metrics (port 9090)
- ✅ **Grafana Dashboards**: Visualização de métricas (port 3000)
- ✅ **Jaeger Tracing**: Distributed tracing OpenTelemetry (port 16686)
- ✅ **Loki Logging**: Centralized log aggregation

### File Management
- ✅ **MinIO Object Storage**: Armazenamento escalável (S3-compatible)
- ✅ **Multipart Uploads**: Suporte para arquivos grandes (>1GB)
- ✅ **Content Validation**: Verificação de tipo MIME e tamanho

**Arquitetura Production**: Ver [specs/002-production-ready/plan.md](specs/002-production-ready/plan.md) para detalhes completos de arquitetura e decisões técnicas.

---

## 🔧 Stack Tecnológica

### Core Platform
- **API Frameworks**: FastAPI 0.104.1 (REST) + gRPC (high-performance RPC)
- **Database**: PostgreSQL 15+ with read replicas + SQLAlchemy 2.0.23
- **Message Broker**: Apache Kafka 3.5+ (guaranteed delivery, partitioning)
  - **Development**: Single-broker setup (docker-compose.yml)
  - **Production**: 3-broker HA cluster with ZooKeeper quorum (docker-compose.kafka-cluster.yml)
  - **Configuration**: RF=3, min.insync.replicas=2, acks='all' (zero data loss)
- **Cache**: Redis 7+ (session store, rate limiting, deduplication)
- **Object Storage**: MinIO 7.2.0 or S3 (file attachments ≤2GB)
- **Orchestration**: Kubernetes 1.28+ (horizontal scaling, auto-failover)

### Observability Stack
- **Metrics**: Prometheus + Grafana (port 9090 for Kafka HA metrics)
- **Tracing**: Jaeger or Tempo (OpenTelemetry)
- **Logging**: ELK Stack or Loki (structured JSON logs)
- **Kafka Monitoring**: Kafka UI web interface (port 8080 in production)

### Security
- **Authentication**: OAuth 2.0
- **Encryption**: TLS 1.3
- **Password Hashing**: bcrypt (cost ≥12) or Argon2

### Development
- **Testing**: pytest 7.4.3 (unit, integration, contract, e2e, chaos)
- **Load Testing**: Locust (API throughput, WebSocket, file upload, sustained load)
- **Type Checking**: mypy --strict
- **Code Quality**: black, pylint, flake8

## 📚 Documentação Adicional

### Core Documentation
- [**Especificação Completa**](specs/001-chat-api-hub/spec.md)
- [**Plano Técnico**](specs/001-chat-api-hub/plan.md)
- [**Modelo de Dados**](specs/001-chat-api-hub/data-model.md)
- [**Pesquisa Técnica**](specs/001-chat-api-hub/research.md)
- [**Tarefas**](specs/001-chat-api-hub/tasks.md)

### Production Documentation
- [**Production-Ready Spec**](specs/002-production-ready/spec.md)
- [**Production Plan**](specs/002-production-ready/plan.md)
- [**Kafka HA Guide**](docs/KAFKA_HA_GUIDE.md) - High availability cluster setup
- [**Load Testing Summary**](LOAD_TESTING_SUMMARY.md) - Performance validation
- [**Load Testing Status**](LOAD_TESTING_STATUS.md) - Infrastructure and deployment options

---

## 📝 Princípios do Projeto

Este projeto segue os princípios documentados em [.specify/memory/constitution.md](.specify/memory/constitution.md):

1. **Ubiquity and Interoperability**: Single unified API abstracting all messaging channels
2. **Reliability and Resilience**: ≥99.95% SLA, at-least-once delivery, automatic failover
3. **Scalability and Performance**: Millions of users, 10M msg/min, <200ms p99 latency
4. **Consistency and Order**: Causal message ordering, strong eventual consistency
5. **Extensibility and Maintainability**: Modular architecture, clean separation of concerns
6. **Security and Privacy**: TLS 1.3, OAuth 2.0, rate limiting, audit logging
7. **Observability**: Full instrumentation with metrics, tracing, and centralized logging

## 👥 Autores

Projeto desenvolvido para a disciplina de Sistemas Distribuídos - FACULDADE

## 📄 Licença

Projeto acadêmico - uso educacional
