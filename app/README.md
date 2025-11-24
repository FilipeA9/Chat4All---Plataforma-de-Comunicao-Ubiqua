# Chat4All API Hub

## 📋 Visão Geral

API de comunicação ubíqua para integração multi-canal (WhatsApp, Instagram, etc.). Projeto acadêmico para a disciplina de Sistemas Distribuídos.

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

Para instruções detalhadas de configuração e execução, consulte:

📖 **[specs/001-chat-api-hub/quickstart.md](specs/001-chat-api-hub/quickstart.md)**

O guia completo inclui:
- Pré-requisitos (Python 3.11+, PostgreSQL, Kafka, MinIO)
- Instalação passo a passo (~30 minutos)
- Verificação de funcionamento
- Troubleshooting

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

## 🔧 Stack Tecnológica

- **API**: FastAPI 0.104.1 + Uvicorn 0.24.0
- **Banco de Dados**: PostgreSQL 15+ + SQLAlchemy 2.0.23
- **Message Broker**: Apache Kafka 3.5+
- **Object Storage**: MinIO 7.2.0
- **Testes**: pytest 7.4.3

## 📝 Princípios do Projeto

Este projeto segue os princípios documentados em [.specify/memory/constitution.md](.specify/memory/constitution.md):

1. **Qualidade de Código**: Python 3.11+, PEP 8, type hints obrigatórios
2. **Arquitetura Modular**: Separação clara entre API/workers/DB
3. **TDD**: Testes são NON-NEGOTIABLE
4. **Stack Compliance**: FastAPI/PostgreSQL/Kafka/MinIO
5. **Documentation-First**: Especificações antes de código
6. **Simplicidade MVP**: POC acadêmico, não produção

## 👥 Autores

Projeto desenvolvido para a disciplina de Sistemas Distribuídos - FACULDADE

## 📄 Licença

Projeto acadêmico - uso educacional
