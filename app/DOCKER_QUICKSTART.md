# 🐳 Guia de Configuração com Docker - Chat4All

Este guia simplifica MUITO a configuração usando Docker. Todo o ambiente será executado em **containers**, eliminando a necessidade de instalar PostgreSQL, Kafka, MinIO manualmente.

⏱️ **Tempo estimado**: ~10 minutos

---

## 📋 Pré-requisitos

Você só precisa instalar:

1. **Docker Desktop** - [Download aqui](https://www.docker.com/products/docker-desktop/)
2. **Python 3.11+** (apenas para desenvolvimento local) - [Download aqui](https://www.python.org/downloads/)

---

## 🚀 Passo 1: Instalar Docker Desktop

### 1.1 Download e Instalação

1. Acesse: https://www.docker.com/products/docker-desktop/
2. Baixe a versão para **Windows**
3. Execute o instalador
4. **Reinicie o computador** quando solicitado

### 1.2 Verificar Instalação

Abra o PowerShell e execute:

```powershell
docker --version
# Deve retornar: Docker version 24.x.x

docker-compose --version
# Deve retornar: Docker Compose version v2.x.x
```

✅ **Verificação**: Se ambos os comandos funcionarem, o Docker está instalado corretamente.

---

## 🗂️ Passo 2: Preparar o Projeto

### 2.1 Navegar até o diretório do projeto

```powershell
cd "c:\Users\DELL\Documents\FACULDADE\sistemas distribuidos\Projeto Final\Chat4All---Plataforma-de-Comunicao-Ubiqua\app"
```

### 2.2 Verificar arquivos criados

Confirme que os seguintes arquivos existem:
- ✅ `docker-compose.yml`
- ✅ `Dockerfile`
- ✅ `.dockerignore`

### 2.3 Criar arquivo `.env`

```powershell
# Copiar template
copy .env.example .env
```

O arquivo `.env` já está configurado corretamente para uso com Docker! Não precisa editar nada.

---

## 🐳 Passo 3: Iniciar Todo o Ambiente

### 3.1 Build das imagens (primeira vez apenas)

```powershell
docker-compose build
```

Este comando pode levar **3-5 minutos** na primeira vez (baixa imagens base e instala dependências).

### 3.2 Iniciar todos os serviços

```powershell
docker-compose up -d
```

O parâmetro `-d` executa em modo **detached** (background).

### 3.3 Verificar status dos containers

```powershell
docker-compose ps
```

Você deve ver algo assim:

```
NAME                        STATUS              PORTS
chat4all-api                Up                  0.0.0.0:8000->8000/tcp
chat4all-kafka              Up                  0.0.0.0:9092->9092/tcp
chat4all-minio              Up                  0.0.0.0:9000-9001->9000-9001/tcp
chat4all-postgres           Up                  0.0.0.0:5432->5432/tcp
chat4all-worker-instagram   Up
chat4all-worker-router      Up
chat4all-worker-whatsapp    Up
chat4all-zookeeper          Up                  0.0.0.0:2181->2181/tcp
```

✅ **Verificação**: Todos os serviços devem estar **Up** (rodando).

---

## 📊 Passo 4: Acompanhar os Logs

### 4.1 Ver logs de todos os serviços

```powershell
docker-compose logs -f
```

Pressione **Ctrl+C** para parar de seguir os logs (os containers continuam rodando).

### 4.2 Ver logs de um serviço específico

```powershell
# API
docker-compose logs -f api

# Message Router
docker-compose logs -f worker-router

# WhatsApp Worker
docker-compose logs -f worker-whatsapp

# Kafka
docker-compose logs -f kafka
```

---

## ✅ Passo 5: Testar a Instalação

### 5.1 Verificar API (Swagger)

Abra no navegador: **http://localhost:8000/docs**

Você deve ver a interface Swagger com todos os endpoints.

### 5.2 Verificar MinIO Console

Abra no navegador: **http://localhost:9001**

- **Login**: `minioadmin`
- **Senha**: `minioadmin`

Você deve ver o bucket `chat4all-files` criado.

### 5.3 Testar Autenticação

```powershell
# Windows PowerShell
$response = Invoke-RestMethod -Uri "http://localhost:8000/auth/token" -Method Post -ContentType "application/json" -Body '{"username":"user1","password":"password123"}'
$token = $response.token
Write-Host "Token: $token"
```

Se receber um token UUID, a autenticação está funcionando! 🎉

### 5.4 Criar uma conversa

```powershell
# Usando o token do passo anterior
$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
}

$body = @{
    type = "private"
    member_ids = @(1, 2)
} | ConvertTo-Json

$conversation = Invoke-RestMethod -Uri "http://localhost:8000/v1/conversations" -Method Post -Headers $headers -Body $body
Write-Host "Conversation ID: $($conversation.id)"
```

### 5.5 Enviar mensagem

```powershell
$messageBody = @{
    message_id = [guid]::NewGuid().ToString()
    conversation_id = $conversation.id
    payload = @{
        type = "text"
        content = "Hello from Docker!"
    }
    channels = @("whatsapp")
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/v1/messages" -Method Post -Headers $headers -Body $messageBody
```

### 5.6 Verificar processamento nos logs

```powershell
# Ver logs do message router
docker-compose logs worker-router --tail 20

# Ver logs do WhatsApp worker
docker-compose logs worker-whatsapp --tail 20
```

Você deve ver as mensagens sendo processadas! ✅

---

## 🛠️ Comandos Úteis

### Gerenciar Containers

```powershell
# Parar todos os serviços
docker-compose stop

# Reiniciar todos os serviços
docker-compose restart

# Parar e remover containers
docker-compose down

# Parar e remover containers + volumes (LIMPA TUDO)
docker-compose down -v

# Reconstruir imagens (após mudanças no código)
docker-compose build

# Reiniciar um serviço específico
docker-compose restart api
docker-compose restart worker-router
```

### Ver Logs

```powershell
# Logs de todos os serviços
docker-compose logs

# Logs seguindo em tempo real
docker-compose logs -f

# Últimas 50 linhas de um serviço
docker-compose logs --tail 50 api

# Logs desde uma data/hora específica
docker-compose logs --since "2025-11-27T15:00:00"
```

### Acessar Shell de um Container

```powershell
# Acessar shell do container da API
docker-compose exec api bash

# Acessar PostgreSQL
docker-compose exec postgres psql -U chat4all_user -d chat4all

# Executar comando sem entrar no shell
docker-compose exec postgres psql -U chat4all_user -d chat4all -c "SELECT * FROM users;"
```

### Monitorar Recursos

```powershell
# Ver uso de CPU/Memória dos containers
docker stats

# Ver apenas containers do projeto
docker stats $(docker-compose ps -q)
```

---

## 🗄️ Acessar Banco de Dados

### Via Docker

```powershell
# Conectar ao PostgreSQL
docker-compose exec postgres psql -U chat4all_user -d chat4all

# Listar tabelas
\dt

# Ver usuários
SELECT * FROM users;

# Sair
\q
```

### Via Cliente Local (opcional)

Se você tem pgAdmin ou DBeaver instalado:

- **Host**: `localhost`
- **Porta**: `5432`
- **Database**: `chat4all`
- **Username**: `chat4all_user`
- **Password**: `chat4all_password`

---

## 🔧 Desenvolvimento Local

### Opção 1: Editar código com auto-reload (Recomendado)

O código é montado como volume no container. Qualquer mudança nos arquivos Python será detectada automaticamente pelo `--reload` do Uvicorn.

```powershell
# Apenas edite os arquivos normalmente
# A API reiniciará automaticamente
```

### Opção 2: Desenvolvimento híbrido (serviços em Docker, código local)

```powershell
# Parar apenas a API
docker-compose stop api worker-router worker-whatsapp worker-instagram

# Criar ambiente virtual local
python -m venv venv
venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt

# Criar .env local (apontando para serviços Docker)
copy .env.example .env

# Executar API localmente
uvicorn main:app --reload

# Em outros terminais, executar workers
python -m workers.message_router
python -m workers.whatsapp_mock
python -m workers.instagram_mock
```

---

## 🧪 Executar Testes

### Testes dentro do container

```powershell
# Executar todos os testes
docker-compose exec api pytest -v

# Testes de API
docker-compose exec api pytest tests/test_api.py -v

# Testes de workers
docker-compose exec api pytest tests/test_workers.py -v
```

### Testes localmente

```powershell
# Ativar ambiente virtual
venv\Scripts\activate

# Executar testes
pytest -v
```

---

## 🐛 Troubleshooting

### Erro: "Port already in use"

```powershell
# Parar containers que possam estar usando as portas
docker-compose down

# Verificar processos usando portas
netstat -ano | findstr :8000
netstat -ano | findstr :5432
netstat -ano | findstr :9092

# Matar processo específico (substitua <PID>)
taskkill /PID <PID> /F

# Reiniciar Docker Desktop
# Menu Docker Desktop → Troubleshoot → Restart Docker
```

### Erro: "No space left on device"

```powershell
# Limpar recursos não utilizados
docker system prune -a --volumes

# CUIDADO: Isso remove TUDO (imagens, containers, volumes não utilizados)
```

### Container não inicia

```powershell
# Ver logs completos
docker-compose logs <service-name>

# Exemplo
docker-compose logs postgres
docker-compose logs kafka

# Recriar container
docker-compose up -d --force-recreate <service-name>
```

### Migrations não foram executadas

```powershell
# Executar migrations manualmente
docker-compose exec postgres psql -U chat4all_user -d chat4all -f /docker-entrypoint-initdb.d/001_initial_schema.sql
docker-compose exec postgres psql -U chat4all_user -d chat4all -f /docker-entrypoint-initdb.d/002_seed_users.sql
```

### Resetar banco de dados

```powershell
# Parar e remover volumes
docker-compose down -v

# Subir novamente (recria tudo)
docker-compose up -d
```

---

## 📦 Estrutura de Containers

| Container | Descrição | Portas | Healthcheck |
|-----------|-----------|--------|-------------|
| **chat4all-postgres** | PostgreSQL 15 | 5432 | ✅ |
| **chat4all-zookeeper** | Zookeeper (coordenação Kafka) | 2181 | ✅ |
| **chat4all-kafka** | Kafka Broker | 9092 | ✅ |
| **chat4all-minio** | MinIO (object storage) | 9000, 9001 | ✅ |
| **chat4all-api** | FastAPI Application | 8000 | ✅ |
| **chat4all-worker-router** | Message Router Worker | - | - |
| **chat4all-worker-whatsapp** | WhatsApp Mock Worker | - | - |
| **chat4all-worker-instagram** | Instagram Mock Worker | - | - |

---

## 📊 Resumo dos Serviços

Após executar `docker-compose up -d`, você terá:

| Serviço | URL/Porta | Credenciais |
|---------|-----------|-------------|
| **API (Swagger)** | http://localhost:8000/docs | - |
| **API (ReDoc)** | http://localhost:8000/redoc | - |
| **MinIO Console** | http://localhost:9001 | minioadmin / minioadmin |
| **PostgreSQL** | localhost:5432 | chat4all_user / chat4all_password |
| **Kafka** | localhost:9092 | - |

---

## 🎯 Comparação: Manual vs Docker

| Aspecto | Manual | Docker |
|---------|--------|--------|
| **Tempo de Setup** | ~30 minutos | ~10 minutos |
| **Terminais Necessários** | 8 terminais | 1 comando |
| **Instalações** | 5 softwares | Apenas Docker |
| **Portabilidade** | Dependente de OS | Funciona em qualquer OS |
| **Limpeza** | Manual (desinstalar tudo) | `docker-compose down -v` |
| **Isolamento** | Compartilha recursos do OS | Containers isolados |

---

## 🏭 Modo Produção: Kafka HA Cluster

Para ambientes de produção com **alta disponibilidade** e **zero data loss**:

### 📖 Guia Completo

Ver **[docs/KAFKA_HA_GUIDE.md](docs/KAFKA_HA_GUIDE.md)** para documentação completa.

### 🚀 Quick Start (Production)

```powershell
# 1. Parar ambiente de desenvolvimento (se estiver rodando)
docker-compose down

# 2. Iniciar Kafka HA Cluster (3 brokers + 3 ZooKeeper)
docker-compose -f docker-compose.kafka-cluster.yml up -d

# 3. Aguardar inicialização (~60 segundos)
Start-Sleep -Seconds 60

# 4. Verificar saúde do cluster
docker-compose -f docker-compose.kafka-cluster.yml ps
```

### 🎯 Recursos de Produção

| Recurso | Desenvolvimento | Produção (HA) |
|---------|----------------|---------------|
| **Kafka Brokers** | 1 broker (single point of failure) | 3 brokers (zero downtime) |
| **ZooKeeper** | 1 node | 3 nodes (quorum) |
| **Replication Factor** | 1 (sem backup) | 3 (dados triplicados) |
| **min.insync.replicas** | 1 | 2 (garante durabilidade) |
| **Failover** | ❌ Manual restart | ✅ Automático (<30s) |
| **Data Loss** | ⚠️ Possível | ✅ Zero perda (acks='all') |
| **Monitoring** | ❌ Básico | ✅ Prometheus + Kafka UI |
| **Web Interface** | ❌ N/A | ✅ http://localhost:8080 |
| **Health Metrics** | ❌ N/A | ✅ http://localhost:9090/metrics |

### 🧪 Testar Failover

```powershell
# 1. Verificar cluster saudável
docker-compose -f docker-compose.kafka-cluster.yml ps

# 2. Matar 1 broker (simular falha)
docker stop app-kafka-2-1

# 3. Sistema continua operando (zero downtime)
# Verificar no Kafka UI: http://localhost:8080

# 4. Reiniciar broker (recuperação automática)
docker start app-kafka-2-1

# 5. Cluster volta ao estado completo (~30 segundos)
```

### 📊 Monitoramento

**Kafka UI** (http://localhost:8080):
- Visualizar brokers, topics, partitions
- Inspecionar mensagens em tempo real
- Monitorar consumer groups e lag

**Health Metrics** (http://localhost:9090/metrics):
- Prometheus-format metrics
- Kafka cluster health status
- Broker availability
- Topic replication status

### ⚠️ Nota Importante

**Não execute ambos os modos simultaneamente**:
- Development (`docker-compose.yml`): Kafka na porta **9092**
- Production (`docker-compose.kafka-cluster.yml`): Kafka nas portas **9092, 9093, 9094**

**Conflito de portas**: Sempre pare um antes de iniciar o outro:

```powershell
# Parar desenvolvimento
docker-compose down

# Iniciar produção
docker-compose -f docker-compose.kafka-cluster.yml up -d

# OU vice-versa
docker-compose -f docker-compose.kafka-cluster.yml down
docker-compose up -d
```

### 🧪 Load Testing

Para validação de performance com Kafka HA:

📖 **[LOAD_TESTING_SUMMARY.md](LOAD_TESTING_SUMMARY.md)**

```powershell
# 1. Garantir que Kafka HA está rodando
docker-compose -f docker-compose.kafka-cluster.yml ps

# 2. Executar testes de carga (~45 minutos)
cd tests\load
.\run_all_tests.ps1

# Testes incluem:
# - API Throughput: 166.666 req/s (5000 users)
# - WebSocket: 10.000 concurrent connections
# - File Upload: 100 concurrent 1GB uploads
# - Sustained Load: 15 minutes continuous
```

**Documentação Completa**:
- [Kafka HA Implementation](docs/KAFKA_HA_IMPLEMENTATION.md)
- [Load Testing Status](LOAD_TESTING_STATUS.md)
- [Production Specification](specs/002-production-ready/spec.md)
- [Production Architecture](specs/002-production-ready/plan.md)

---

## 🚀 Próximos Passos

Agora que o ambiente está rodando:

1. ✅ **Explore a API**: http://localhost:8000/docs
2. ✅ **Teste os endpoints** usando Swagger ou curl/Invoke-RestMethod
3. ✅ **Acompanhe os logs** dos workers processando mensagens
4. ✅ **Desenvolva novas features** (código monta automaticamente no container)
5. ✅ **Upgrade para Produção**: Siga o guia de Kafka HA para high availability

---

## 📚 Usuários de Teste

Os seguintes usuários estão disponíveis (seed automático):

```
username: user1, password: password123
username: user2, password: password123
username: user3, password: password123
username: admin, password: admin123
```

---

## 🛑 Parar o Ambiente

```powershell
# Parar containers (mantém dados)
docker-compose stop

# Parar e remover containers (mantém volumes/dados)
docker-compose down

# Parar e LIMPAR TUDO (remove volumes e dados)
docker-compose down -v
```

---

## ✨ Vantagens do Docker

✅ **Sem conflitos de porta** - Tudo isolado  
✅ **Reprodutível** - Mesmo ambiente em qualquer máquina  
✅ **Rápido reset** - `docker-compose down -v && docker-compose up -d`  
✅ **Fácil compartilhar** - Basta o `docker-compose.yml`  
✅ **Produção-ready** - Pode deployar com poucas mudanças  

Boa sorte com o projeto! 🚀🐳
