# Relatório Técnico — Arquitetura, Fluxos, Testes e Decisões do Projeto: Chat4All v2

**Autores:** Filipe Augusto Lima Silva , Amanda Almeida dos Santos, Guilherme Luís Andrade Borges.

**Data:** 05 de Dezembro de 2025

**Versão:** 1.0

---


## 1. **Introdução e Objetivos**

Este projeto implementa uma plataforma de mensageria de alta escala, construída para lidar com milhares de mensagens por segundo, manter ordenação por conversa, garantir consistência at-least-once com deduplicação e permitir crescimento horizontal.
A solução combina API assíncrona, Event Streaming com Kafka, padrão Outbox, Redis para comunicação interna e Observabilidade completa (Prometheus, Grafana e Alertmanager).

Os objetivos principais do sistema são:

* Receber mensagens de clientes com baixa latência.
* Garantir persistência confiável e entrega consistente.
* Manter ordenação causal por conversa.
* Escalar horizontalmente API, workers e pipelines.
* Fornecer rastreamento, métricas e alertas de ponta a ponta.
* Permitir tolerância a falhas e rápida recuperação.

---

## 2. **Arquitetura Final Implementada**

A arquitetura do sistema é composta por **cinco blocos principais**:

### **2.1 API (FastAPI)**

* Endpoints de criação de mensagens, autenticação e health checks.
* Persistência da mensagem e da entrada de Outbox dentro da mesma transação.
* Exposição de métricas Prometheus.
* Lógica de deduplicação com `message_id`.
* Rate limiting e auditoria.
  **Arquivos relevantes:**
  `api/main.py`, `api/endpoints.py`, `api/metrics.py`, `api/auth.py`, `core/audit_logger.py`

### **2.2 Banco de Dados (Postgres)**

* Armazena mensagens e tabela Outbox (`OutboxEvent`).
* Implementa o padrão **Transactional Outbox** garantindo consistência at-least-once.
  **Arquivos relevantes:**
  `db/models.py`, `db/session.py`

### **2.3 Workers**

* **Outbox Poller**: lê a tabela Outbox, publica no Kafka com idempotência e confirma publicação.
* **Message Router**: recebe eventos e envia mensagens para tópicos particionados (partitioning por `conversation_id`).
* **Redis Backfill Worker**: recupera estados temporários guardados no Redis após falhas.
  **Arquivos relevantes:**
  `workers/outbox_poller.py`, `workers/message_router.py`, `workers/redis_backfill.py`

### **2.4 Kafka (event streaming)**

* Pipeline assíncrono de entrega de mensagens.
* Uso de partition key: `conversation:{conversation_id}` para manter **ordem causal** dentro da conversa.
* Producer com `enable_idempotence=True` e `acks=all`.
  **Arquivos relevantes:**
  `workers/message_router.py`, `workers/outbox_poller.py`

### **2.5 Redis**

* Cache e estado temporário.
* Pub/Sub interno para operações rápidas.
* Armazenamento auxiliar para backfill.
  **Arquivos relevantes:**
  `services/redis_client.py`, `workers/redis_backfill.py`

### **2.6 Observabilidade**

* Prometheus: coleta de métricas.
* Alertmanager: envio de alertas.
* Grafana: dashboards.
* OpenTelemetry: tracing e instrumentação.
  **Arquivos relevantes:**
  `observability/`, `api/metrics.py`, `core/logging`, OTel configs.

---

## 3. **Decisões Técnicas**

As escolhas arquiteturais do projeto seguem critérios de desempenho, escalabilidade e consistência.

### **3.1 FastAPI + Assincronismo**

* Minimiza latência de I/O.
* Adequado para workloads de milhares de requisições por segundo.

### **3.2 Transactional Outbox**

* Garante **consistência at-least-once**.
* Evita o problema clássico de “dupla escrita” (DB + Kafka).

### **3.3 Kafka como backbone**

* Permite throughput alto e ordenação por partição.
* Suporta escalabilidade horizontal via consumer groups.

### **3.4 Partition Key por conversa**

* Garante ordenação causal obrigatória para mensageria.
* Cada conversa sempre vai para a mesma partição.

### **3.5 Redis como acelerador**

* Evita carga excessiva no banco.
* Suporta recuperação e pub/sub leve.

### **3.6 Observabilidade nativa**

* Métricas, logs e tracing integrados desde o início.
* Alertas configuráveis por Prometheus/Alertmanager.

### **3.7 Segurança**

* Autenticação via OAuth2/JWT.
* Suporte a TLS no gateway (certificados disponíveis).
* Auditoria de eventos sensíveis.

---

## 4. **Testes de Carga e Métricas Coletadas**

*(O projeto contém instrumentação, mas não contém artefatos de testes. O conteúdo abaixo descreve o que o sistema mede e como medir.)*

### **4.1 Métricas disponíveis**

A API expõe métricas via `/metrics`:

* Latência HTTP (histogram).
* Contadores por endpoint.
* Erros de aplicação.
* Métricas de workers (process uptime, eventos publicados, falhas, retries).
* Lag de consumidores de Kafka (via exporters).
* Redis health e tempo de resposta.

### **4.2 Processo sugerido de teste de carga**

Ferramentas recomendadas:

* `k6`, `wrk`, `ghz`, `locust`.

Caminho medido:

* `cliente → API → DB → Outbox → Worker → Kafka`

As principais métricas semânticas disponíveis:

* **p50 / p95 / p99** de latência da API.
* Throughput de produção no Kafka (msg/s).
* Tempo médio de publicação do outbox.
* Tamanho da fila e lag por worker.
* Porcentagem de deduplicação.

### **4.3 Resultados típicos esperados**

Com a arquitetura implementada:

* Latência API típica: **10–40ms** no ambiente real (sem contenção).
* Throughput: milhares de mensagens/s com scaling horizontal.
* Outbox processando em bateladas (poll interval configurável).

---

## 5. **Falhas Simuladas e Recuperação**

A arquitetura prevê mecanismos de tolerância a falhas:

### **5.1 Falha no Kafka**

* O Outbox Poller continua tentando publicar.
* Sem perda de mensagens graças à persistência no DB.

### **5.2 Falha no Redis**

* Circuit breaker evita travar a API.
* Backfill tenta reconstruir estados assim que o Redis volta.

### **5.3 Falha de worker**

* Outro worker do consumer group assume automaticamente (Kafka).
* Outbox segue acumulando eventos sem perda.

### **5.4 Falha parcial na API**

* Health checks permitem remoção automática de instâncias defeituosas.
* Mensagens já persistidas continuam fluindo pelos workers.

### **5.5 Crash durante escrita**

* Commit da mensagem e da entrada do Outbox ocorre **numa única transação**.
* Evita mensagens órfãs ou publicações inconsistentes.

---

## 6. **Limitações e Melhorias Futuras**

### **6.1 Infraestrutura local**

* O projeto está configurado para ambiente **docker-compose**, não para cluster real.
* Falta HA de Kafka, Redis Cluster/Sentinel e Postgres com failover.

### **6.2 Gateway TLS**

* Certificados existem, mas a **terminação TLS no gateway não está implementada**.
* Recomendado adicionar:

  * NGINX/Traefik/Ingress Controller
  * Renovação automática de certificados

### **6.3 Tracing incompleto nos workers**

* Há instrumentação parcial; recomendável integrar todos os passos:
  API → Outbox → Poller → Kafka → Router → Consumer final.

### **6.4 Sequenciamento explícito**

* Ordem por conversa depende do Kafka.
* Não existe `sequence_number`.
* Caso seja necessário reprocessar ou migrar conversas, um campo seq seria útil.

### **6.5 Backpressure**

* A API não implementa controle explícito de saturação do sistema.

### **6.6 Ausência de testes automatizados de carga**

* A instrumentação existe, mas não há scripts de carga.
* Recomendado criar pipelines de benchmark contínuo.