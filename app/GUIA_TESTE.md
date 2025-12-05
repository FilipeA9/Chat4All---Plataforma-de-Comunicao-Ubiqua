# 🚀 Guia de Teste - Chat4All

## Passo 1: Iniciar os Serviços

### Opção A: Ambiente de Desenvolvimento (Single-Broker)
```bash
docker-compose up -d
```

### Opção B: Ambiente de Produção (Kafka HA Cluster)
```bash
docker-compose -f docker-compose.kafka-cluster.yml up -d
```

**Recomendação**: Começar com Opção A para testes iniciais.

---

## Passo 2: Verificar Status dos Containers

```bash
docker-compose ps
```

Você deve ver:
- ✅ chat4all_postgres (port 5432)
- ✅ chat4all_redis (port 6379)
- ✅ chat4all_zookeeper (port 2181)
- ✅ chat4all_kafka (port 9092)
- ✅ chat4all_minio (port 9000, 9001)
- ✅ chat4all_api (port 8000)
- ✅ chat4all_worker_router
- ✅ chat4all_worker_whatsapp
- ✅ chat4all_worker_instagram
- ✅ chat4all_worker_outbox
- ✅ chat4all_worker_status
- ✅ chat4all_prometheus (port 9090)
- ✅ chat4all_grafana (port 3000)
- ✅ chat4all_jaeger (port 16686)
- ✅ chat4all_loki (port 3100)
- ✅ chat4all_alertmanager (port 9095)

---

## Passo 3: Aguardar Inicialização (~60 segundos)

Verifique os logs para garantir que todos os serviços iniciaram:

```bash
# Ver logs da API
docker-compose logs -f api

# Ver logs dos workers
docker-compose logs -f worker-router worker-whatsapp worker-instagram

# Ver todos os logs
docker-compose logs -f
```

---

## Passo 4: Verificar Health Checks

### API Health Check
```bash
curl http://localhost:8000/health
```

**Resposta esperada**:
```json
{
  "status": "healthy",
  "service": "Chat4All API",
  "version": "2.0.0",
  "environment": "development"
}
```

### Readiness Check
```bash
curl http://localhost:8000/ready
```

**Resposta esperada**:
```json
{
  "status": "ready",
  "checks": {
    "database": {"healthy": true, "message": "Database connection OK"},
    "redis": {"healthy": true, "message": "Redis connection OK"},
    "kafka": {"healthy": true, "message": "Kafka connection OK"}
  }
}
```

---

## Passo 5: Acessar Interfaces Web

### Documentação Interativa da API
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Grafana (Dashboards)
- **URL**: http://localhost:3000
- **Usuário**: admin
- **Senha**: admin

### Prometheus (Métricas)
- **URL**: http://localhost:9090

### Jaeger (Distributed Tracing)
- **URL**: http://localhost:16686

### MinIO (Object Storage)
- **URL**: http://localhost:9001
- **Usuário**: minioadmin
- **Senha**: minioadmin

---

## Passo 6: Executar Testes da API

### Teste 1: Autenticar Usuário
```bash
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "user1",
    "client_secret": "password123",
    "scope": "read write"
  }'
```

**Salve o `access_token` retornado para os próximos testes.**

### Teste 2: Criar Conversa
```bash
curl -X POST http://localhost:8000/v1/conversations \
  -H "Authorization: Bearer SEU_TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "private",
    "member_ids": [1, 2]
  }'
```

### Teste 3: Enviar Mensagem
```bash
curl -X POST http://localhost:8000/v1/messages \
  -H "Authorization: Bearer SEU_TOKEN_AQUI" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "550e8400-e29b-41d4-a716-446655440000",
    "conversation_id": 1,
    "payload": {"type": "text", "content": "Hello, World!"},
    "channels": ["whatsapp"]
  }'
```

### Teste 4: Listar Conversas
```bash
curl -X GET "http://localhost:8000/v1/conversations?limit=20&offset=0" \
  -H "Authorization: Bearer SEU_TOKEN_AQUI"
```

### Teste 5: Listar Mensagens
```bash
curl -X GET "http://localhost:8000/v1/conversations/1/messages?limit=50&offset=0" \
  -H "Authorization: Bearer SEU_TOKEN_AQUI"
```

---

## Passo 7: Executar Testes Automatizados

### Testes Unitários/Integração (Pytest)
```bash
# Instalar dependências (se necessário)
pip install -r requirements.txt

# Executar testes
pytest -v tests/
```

### Load Tests (Locust)
```bash
cd tests/load

# Instalar Locust
pip install locust

# Teste 1: API Throughput (5 min, 5000 usuários)
locust -f test_api_throughput.py --headless -u 5000 -r 100 -t 5m --host http://localhost:8000

# Teste 2: WebSocket Connections (5 min, 10000 conexões)
locust -f test_websocket_connections.py --headless -u 10000 -r 200 -t 5m --host ws://localhost:8000

# Teste 3: File Upload (10 min, 100 usuários)
locust -f test_file_upload.py --headless -u 100 -r 10 -t 10m --host http://localhost:8000

# Executar TODOS os testes de uma vez (Windows)
.\run_all_tests.ps1

# Executar TODOS os testes (Linux/Mac)
./run_all_tests.sh
```

---

## Passo 8: Monitorar o Sistema

### Ver Métricas Prometheus
1. Acesse: http://localhost:9090
2. Execute queries:
   - `http_request_duration_seconds_sum` (latência HTTP)
   - `websocket_connections_active` (conexões WebSocket ativas)
   - `outbox_pending_events` (eventos pendentes na fila)

### Ver Traces no Jaeger
1. Acesse: http://localhost:16686
2. Selecione serviço: `chat4all-api`
3. Busque traces para ver o fluxo completo

### Ver Dashboards no Grafana
1. Acesse: http://localhost:3000
2. Login: admin/admin
3. Navegue até Dashboards:
   - API Health
   - Database Performance
   - Kafka Lag
   - Message Pipeline

---

## Troubleshooting

### Erro: "Connection refused" ao acessar API

**Solução**:
```bash
# Ver logs da API
docker-compose logs api

# Reiniciar serviço
docker-compose restart api
```

### Erro: Kafka não conecta

**Solução**:
```bash
# Ver logs do Kafka
docker-compose logs kafka

# Aguardar mais tempo (Kafka demora ~30s para iniciar)
sleep 30
docker-compose ps
```

### Erro: Database migration failed

**Solução**:
```bash
# Resetar database
docker-compose down -v
docker-compose up -d postgres
sleep 10
docker-compose up -d
```

### Limpar e Reiniciar do Zero

```bash
# Parar todos os containers
docker-compose down

# Remover volumes (CUIDADO: apaga dados!)
docker-compose down -v

# Iniciar novamente
docker-compose up -d
```

---

## Comandos Úteis

```bash
# Ver status
docker-compose ps

# Ver logs de um serviço específico
docker-compose logs -f api

# Parar todos os serviços
docker-compose stop

# Iniciar todos os serviços
docker-compose start

# Reiniciar um serviço
docker-compose restart api

# Executar comando dentro de um container
docker-compose exec api python -c "print('Hello')"

# Acessar shell do container
docker-compose exec api bash

# Ver uso de recursos
docker stats
```

---

## Próximos Passos

1. ✅ Explorar a documentação interativa (Swagger)
2. ✅ Testar upload de arquivos
3. ✅ Conectar via WebSocket para mensagens em tempo real
4. ✅ Ver métricas e traces de performance
5. ✅ Executar load tests para validar escalabilidade

---

**Nota**: Este guia assume ambiente de desenvolvimento. Para produção, consulte `docs/KAFKA_HA_GUIDE.md` e configure TLS/SSL.
