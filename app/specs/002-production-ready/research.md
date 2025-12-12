# Research: Production-Ready Platform Evolution

**Feature**: Production-Ready Platform Evolution  
**Branch**: `002-production-ready`  
**Date**: 2025-11-30

## Overview

This document consolidates research findings for technical decisions required to evolve Chat4All v2 into a production-ready distributed messaging platform. All research tasks are driven by the Technical Context in `plan.md` and aim to resolve implementation details for OAuth 2.0 authentication, Transactional Outbox pattern, WebSocket scaling, PostgreSQL high availability, and Kafka clustering.

---

## R1: OAuth 2.0 JWT Library Selection (Python)

### Decision: **authlib**

### Rationale

**authlib** is chosen over python-jose for the following reasons:

1. **Comprehensive OAuth 2.0 Support**: authlib is specifically designed for OAuth 2.0/OpenID Connect and provides built-in support for Client Credentials flow, token introspection, and token revocation. python-jose is a general-purpose JWT library without OAuth-specific abstractions.

2. **Active Maintenance**: authlib is actively maintained by Authlib Community (latest release: 2023) with frequent updates and security patches. python-jose development has slowed significantly (last major update: 2021).

3. **Type Safety**: authlib has better type hints and mypy compatibility, aligning with the project's strict type checking requirements (mypy --strict).

4. **Performance**: authlib uses native cryptography libraries (cryptography package) for performance-critical operations, while python-jose has slower pure-Python implementations for some algorithms.

5. **FastAPI Integration**: authlib has documented integration patterns with FastAPI for OAuth 2.0 flows, reducing boilerplate code.

### Alternatives Considered

- **python-jose**: Simpler API for basic JWT operations but lacks OAuth 2.0 abstractions. Would require manual implementation of Client Credentials flow, token revocation, and refresh token management. Rejected due to maintenance concerns and lack of OAuth-specific features.

- **PyJWT**: Minimal JWT library with no OAuth 2.0 support. Rejected due to requiring significant custom code for OAuth flows.

### Implementation Notes

```python
# authlib usage for JWT encoding/decoding
from authlib.jose import jwt

# Create JWT token
header = {'alg': 'HS256'}
payload = {
    'user_id': 'user123',
    'tenant_id': 'tenant1',
    'iat': int(time.time()),
    'exp': int(time.time()) + 900,  # 15 minutes
    'scope': 'read write'
}
token = jwt.encode(header, payload, secret_key)

# Validate JWT token
claims = jwt.decode(token, secret_key)
claims.validate()  # Checks expiration, signature
```

**Dependencies**: `authlib>=1.2.1`, `cryptography>=41.0.0`

---

## R2: Transactional Outbox Pattern Implementation

### Decision: **PostgreSQL-based Outbox with dedicated poller worker**

### Rationale

1. **ACID Guarantees**: By writing message data and outbox entry in the same database transaction, we guarantee atomicity. If the transaction fails, neither the message nor the outbox entry is persisted, eliminating the risk of lost messages.

2. **Separation of Concerns**: The outbox poller is a separate worker process that polls the `outbox_events` table and publishes to Kafka. This decouples API responsiveness from Kafka availability—the API can respond with 202 Accepted immediately after the database commit.

3. **Retry Logic**: The poller can implement sophisticated retry logic with exponential backoff without blocking API threads. Failed events remain in the outbox table until successfully published.

4. **Observability**: The outbox table acts as an audit log of all message processing attempts. We can query it to identify stuck messages or measure Kafka publish latency.

### Alternatives Considered

- **Two-Phase Commit (2PC)**: Distributed transaction between PostgreSQL and Kafka. Rejected due to performance overhead (requires blocking until Kafka acknowledges), increased complexity, and Kafka's lack of native 2PC support.

- **Saga Pattern with Compensation**: Publish to Kafka first, then write to PostgreSQL with compensation on failure. Rejected because Kafka messages are difficult to "undo" once published (would require a compensating message), and compensation logic is error-prone.

- **Change Data Capture (CDC)**: Use Debezium to stream PostgreSQL changes to Kafka. Rejected for MVP due to operational complexity (requires Kafka Connect cluster) and increased system dependencies. CDC is a future optimization path once basic outbox is stable.

### Implementation Schema

```sql
-- Outbox events table
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(50) NOT NULL,  -- e.g., 'message', 'conversation'
    aggregate_id UUID NOT NULL,           -- e.g., message.id
    event_type VARCHAR(50) NOT NULL,      -- e.g., 'message.created', 'message.delivered'
    payload JSONB NOT NULL,               -- Full event data
    published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    version INTEGER DEFAULT 1,
    INDEX idx_outbox_unpublished (published, created_at) WHERE published = FALSE
);

-- Ensure idempotent publishing
CREATE UNIQUE INDEX idx_outbox_dedup ON outbox_events(aggregate_id, event_type);
```

### Poller Implementation Pattern

```python
# Pseudo-code for outbox poller worker
import asyncio
from sqlalchemy import select, update
from kafka import KafkaProducer

async def poll_outbox(db_session, kafka_producer):
    while True:
        # Fetch batch of unpublished events
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.published == False)
            .order_by(OutboxEvent.created_at)
            .limit(100)
            .with_for_update(skip_locked=True)  # Lock rows, skip if already locked
        )
        events = await db_session.execute(stmt)
        
        for event in events.scalars():
            try:
                # Publish to Kafka
                kafka_producer.send(
                    topic=f"{event.aggregate_type}_processing",
                    key=event.aggregate_id.bytes,
                    value=event.payload
                )
                
                # Mark as published
                event.published = True
                event.published_at = datetime.utcnow()
                await db_session.commit()
            except KafkaException as e:
                # Retry with exponential backoff
                await asyncio.sleep(2 ** event.version)  # 2s, 4s, 8s...
                event.version += 1
                await db_session.commit()
        
        await asyncio.sleep(0.1)  # Poll every 100ms
```

**Key Features**:
- `SELECT ... FOR UPDATE SKIP LOCKED`: Allows multiple poller instances without row-level contention
- Batch processing: Fetch 100 events per batch for efficiency
- Idempotent publishing: UNIQUE constraint on (aggregate_id, event_type) prevents duplicates in outbox
- Exponential backoff: Progressively longer delays for failing events

---

## R3: WebSocket Scaling with Redis Pub/Sub

### Decision: **Redis Pub/Sub for multi-instance fan-out**

### Rationale

1. **Multi-Instance Problem**: With 3+ API instances behind a load balancer, a user's WebSocket connection might be on Instance A, but a message notification originates on Instance B. Without coordination, Instance B cannot push the notification to the user.

2. **Redis Pub/Sub Solution**: When any API instance receives a message event (from Kafka consumer or internal event), it publishes the event to a Redis Pub/Sub channel (e.g., `conversation:{conversation_id}:events`). All API instances subscribe to relevant channels and forward events to their locally connected WebSocket clients.

3. **Stateless API Instances**: API instances remain stateless—they don't need to know which instance has which client. Redis acts as the coordination layer.

4. **Low Latency**: Redis Pub/Sub has <1ms latency for local deployments and <10ms for cross-region, meeting the <100ms notification requirement.

### Alternatives Considered

- **Sticky Sessions**: Route all requests from a user to the same API instance. Rejected because it reduces load balancing effectiveness, creates uneven load distribution, and introduces state (session affinity) into the load balancer.

- **Kafka for WebSocket Fan-Out**: Use Kafka as the notification bus. Rejected because Kafka is optimized for durable, ordered message queues, not ephemeral pub/sub. Kafka's offset management adds unnecessary complexity for real-time notifications.

- **Direct Instance-to-Instance RPC**: API instances discover each other and send gRPC calls directly. Rejected due to operational complexity (service discovery, connection pooling) and increased coupling between instances.

### Implementation Pattern

```python
# Redis Pub/Sub subscriber (runs in background task per API instance)
import redis.asyncio as redis
from fastapi import WebSocket

pubsub = await redis_client.pubsub()

async def redis_listener(websocket_manager: WebSocketManager):
    # Subscribe to all active conversation channels
    # (subscriptions updated dynamically as users connect/disconnect)
    async for message in pubsub.listen():
        if message['type'] == 'message':
            conversation_id = extract_conversation_id(message['channel'])
            event_data = json.loads(message['data'])
            
            # Forward to locally connected clients
            await websocket_manager.broadcast_to_conversation(
                conversation_id=conversation_id,
                event=event_data
            )

# Redis Pub/Sub publisher (called when message is created)
async def notify_message_created(conversation_id: str, message: dict):
    await redis_client.publish(
        channel=f"conversation:{conversation_id}:events",
        message=json.dumps({
            'type': 'message.created',
            'data': message
        })
    )
```

**Connection Manager Pattern**:

```python
# WebSocket connection manager tracks active connections
class WebSocketManager:
    def __init__(self):
        # Map conversation_id -> set of WebSocket connections
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        # User subscribes to their conversations
        user_conversations = await get_user_conversations(user_id)
        for conv_id in user_conversations:
            self.connections[conv_id].add(websocket)
    
    async def disconnect(self, websocket: WebSocket):
        # Remove from all conversations
        for connections in self.connections.values():
            connections.discard(websocket)
    
    async def broadcast_to_conversation(self, conversation_id: str, event: dict):
        # Send to all locally connected clients in this conversation
        for ws in self.connections.get(conversation_id, []):
            await ws.send_json(event)
```

**Scaling Properties**:
- Each API instance subscribes only to channels for its active conversations (memory-efficient)
- Redis Pub/Sub supports millions of channels (one per conversation)
- No message persistence—if no clients are connected, the notification is lost (acceptable for real-time)

---

## R4: PostgreSQL High Availability Setup

### Decision: **Patroni for automated PostgreSQL HA with 1 primary + 2 replicas**

### Rationale

1. **Automated Failover**: Patroni uses etcd/Consul/ZooKeeper for distributed consensus and automatically promotes a replica to primary within 30 seconds of primary failure, meeting the ≥99.95% SLA requirement.

2. **Built for Kubernetes**: Patroni integrates seamlessly with Kubernetes via StatefulSets and ConfigMaps. It uses Kubernetes endpoints for service discovery, making it the de facto standard for PostgreSQL HA in K8s.

3. **Streaming Replication**: Patroni uses PostgreSQL's native streaming replication (synchronous or asynchronous) for replicas, ensuring data durability and read scalability.

4. **Health Checks**: Patroni exposes HTTP health check endpoints for primary/replica status, enabling Kubernetes liveness/readiness probes.

5. **Active Community**: Patroni is actively maintained by Zalando and widely adopted in production (Spotify, GitLab use it).

### Alternatives Considered

- **Stolon**: Similar to Patroni but with less community momentum and fewer Kubernetes-native features. Rejected in favor of Patroni's broader adoption.

- **PostgreSQL Built-in Replication + Manual Failover**: Use `pg_basebackup` and `pg_ctl promote` manually. Rejected because manual failover violates the 30-second recovery time objective (RTO) and requires on-call intervention.

- **Managed PostgreSQL (AWS RDS, Azure Database)**: Cloud-managed HA with automatic failover. Deferred for now to maintain infrastructure portability (on-prem, multi-cloud). This is a future optimization path for cloud deployments.

### Deployment Architecture

```
┌─────────────────────────────────────────┐
│         Kubernetes Cluster              │
│  ┌─────────────────────────────────┐   │
│  │   Patroni Cluster (StatefulSet) │   │
│  │                                  │   │
│  │  ┌──────────┐  ┌──────────┐    │   │
│  │  │ Primary  │  │ Replica1 │    │   │
│  │  │ (RW)     │──│ (RO)     │    │   │
│  │  └──────────┘  └──────────┘    │   │
│  │       │             │           │   │
│  │       │        ┌────┴────┐     │   │
│  │       │        │ Replica2│     │   │
│  │       │        │ (RO)    │     │   │
│  │       │        └─────────┘     │   │
│  │       │                        │   │
│  │   [Streaming Replication]      │   │
│  └───────────────────────────────┘   │
│                                       │
│  ┌─────────────────────────────────┐ │
│  │  etcd (Distributed Lock)        │ │
│  │  (manages leader election)      │ │
│  └─────────────────────────────────┘ │
└───────────────────────────────────────┘
```

### Configuration Example (Patroni YAML)

```yaml
scope: chat4all-postgres
namespace: /db/
name: postgres-0  # Unique per replica

restapi:
  listen: 0.0.0.0:8008
  connect_address: postgres-0.postgres-svc:8008

etcd:
  hosts: etcd-0:2379,etcd-1:2379,etcd-2:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576  # 1MB max lag before failover
    postgresql:
      use_pg_rewind: true
      parameters:
        max_connections: 200
        shared_buffers: 2GB
        wal_level: replica
        max_wal_senders: 10
        max_replication_slots: 10

postgresql:
  listen: 0.0.0.0:5432
  connect_address: postgres-0.postgres-svc:5432
  data_dir: /var/lib/postgresql/data
  authentication:
    replication:
      username: replicator
      password: <replication-password>
    superuser:
      username: postgres
      password: <admin-password>
```

**Failover Process**:
1. Primary fails (pod crashes, node failure, network partition)
2. Patroni replicas detect leader loss via etcd (TTL expires after 30s)
3. Patroni triggers leader election among replicas
4. Replica with least lag is promoted to primary
5. Kubernetes Service updates DNS to point to new primary
6. Applications reconnect automatically (PostgreSQL connection pooling handles reconnection)

**Read Scaling**: Applications can connect to replicas for read-only queries (SELECT) to reduce primary load. Use separate connection strings:
- Write: `postgres-primary-svc:5432`
- Read: `postgres-replica-svc:5432` (load-balanced across replicas)

---

## R5: Kafka Cluster Configuration

### Decision: **3-broker Kafka cluster with replication factor 3, min.insync.replicas 2**

### Rationale

1. **No Single Point of Failure**: With 3 brokers and replication factor 3, the cluster can tolerate 1 broker failure without data loss or downtime. This satisfies the ≥99.95% availability SLA.

2. **Durability Guarantee**: `min.insync.replicas=2` ensures that a write is acknowledged only after at least 2 replicas (including leader) have persisted the message. This provides at-least-once delivery even if the leader fails immediately after acknowledging.

3. **Partition Tolerance**: Kafka's quorum-based replication (leader + 2 replicas) survives network partitions as long as a majority (2 out of 3) of replicas remain connected.

4. **Performance**: 3 brokers provide enough partitioning for 100+ partitions (conversation-level partitioning) while maintaining manageable operational complexity.

### Alternatives Considered

- **2-broker cluster with RF=2**: Rejected because it cannot tolerate any broker failure without risking data loss (if the remaining broker fails before replication completes).

- **5-broker cluster with RF=5**: Over-engineered for initial scale. Rejected due to increased operational complexity (5 nodes to manage) and higher infrastructure cost. 3-broker cluster is the minimum for production-grade durability.

- **Single-broker Kafka**: Rejected immediately—single point of failure, violates constitution Principle II (Reliability).

### Kafka Topic Configuration

```bash
# Create topic with 100 partitions for conversation-level partitioning
kafka-topics.sh --create \
  --topic message_processing \
  --bootstrap-server kafka-0:9092 \
  --partitions 100 \
  --replication-factor 3 \
  --config min.insync.replicas=2 \
  --config retention.ms=604800000  # 7 days retention

# Producer configuration for durability
producer_config = {
    'bootstrap_servers': ['kafka-0:9092', 'kafka-1:9092', 'kafka-2:9092'],
    'acks': 'all',  # Wait for all in-sync replicas
    'retries': 3,
    'max_in_flight_requests_per_connection': 1,  # Preserve order
    'enable_idempotence': True,  # Prevent duplicates on retry
    'compression_type': 'snappy'  # Reduce bandwidth
}

# Consumer configuration for at-least-once processing
consumer_config = {
    'bootstrap_servers': ['kafka-0:9092', 'kafka-1:9092', 'kafka-2:9092'],
    'group_id': 'message-workers',
    'enable_auto_commit': False,  # Manual commit after processing
    'auto_offset_reset': 'earliest',  # Read from beginning on first start
    'max_poll_records': 100  # Batch processing
}
```

### Partition Strategy

**Key**: `conversation_id` as partition key ensures all messages for a conversation go to the same partition, preserving order (constitution Principle IV).

```python
# Producer partitioning
producer.send(
    topic='message_processing',
    key=conversation_id.encode('utf-8'),  # Partition by conversation
    value=message_data
)

# With 100 partitions, conversations are evenly distributed via hash(conversation_id) % 100
# Allows horizontal scaling: 100 worker instances can process different partitions in parallel
```

### Monitoring Key Metrics

1. **Under-Replicated Partitions**: Alert if any partition has fewer than 3 replicas (indicates broker failure or replication lag)
2. **Consumer Lag**: Alert if lag exceeds 10,000 messages (indicates worker processing bottleneck)
3. **ISR Shrink**: Alert if In-Sync Replica set shrinks (indicates replica falling behind leader)
4. **Broker Disk Usage**: Alert at 80% capacity to prevent write failures

---

## R6: Kubernetes Horizontal Pod Autoscaling (HPA)

### Decision: **HPA based on CPU utilization (70% target) with custom metrics as future optimization**

### Rationale

1. **Simplicity**: CPU-based autoscaling is the simplest and most reliable metric for stateless services (API pods, worker pods). It requires no custom metrics server setup.

2. **Effective for API Services**: API request processing is CPU-bound (JWT validation, database queries, Kafka publishing). CPU utilization correlates strongly with request load.

3. **Fast Response**: HPA checks metrics every 15 seconds and scales up/down based on rolling averages, meeting the <60-second scale-up requirement.

4. **Kubernetes Native**: HPA is a built-in Kubernetes resource, no additional components required.

### Configuration Example

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: chat4all-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70  # Scale up at 70% CPU
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 30  # Wait 30s before scaling up
      policies:
      - type: Percent
        value: 50  # Scale up by 50% each time
        periodSeconds: 30
    scaleDown:
      stabilizationWindowSeconds: 300  # Wait 5 min before scaling down
      policies:
      - type: Percent
        value: 10  # Scale down by 10% each time
        periodSeconds: 60
```

**Future Optimization**: Use custom metrics (Prometheus Adapter) to scale based on Kafka consumer lag or WebSocket connection count for more precise scaling.

---

## R7: Load Testing Strategy (10M messages/minute validation)

### Decision: **Locust for API load testing, custom Kafka producer script for throughput testing**

### Rationale

1. **Locust for API Tests**: Locust is Python-based, easy to script, and provides a web UI for real-time metrics. It can simulate millions of concurrent users sending HTTP/WebSocket requests.

2. **Custom Kafka Script for Throughput**: To test 10M msg/min Kafka throughput, we need a dedicated producer script that bypasses the API and directly publishes to Kafka. This isolates Kafka performance from API bottlenecks.

3. **Distributed Load Generation**: Locust supports distributed mode (master + multiple workers) to generate load from multiple machines, necessary to reach 10M msg/min.

### Load Test Scenarios

**Scenario 1: API Ingestion Load**
- **Goal**: Validate <200ms p99 API latency at 100K requests/minute
- **Tool**: Locust
- **Script**:
  ```python
  from locust import HttpUser, task, between
  
  class ChatUser(HttpUser):
      wait_time = between(1, 5)  # 1-5 seconds between requests
      
      def on_start(self):
          # Authenticate and get JWT token
          response = self.client.post("/auth/token", json={
              "client_id": "test-client",
              "client_secret": "test-secret"
          })
          self.token = response.json()["access_token"]
      
      @task(10)
      def send_message(self):
          self.client.post(
              "/v1/messages",
              headers={"Authorization": f"Bearer {self.token}"},
              json={
                  "conversation_id": "conv-123",
                  "content": "Test message",
                  "channels": ["whatsapp"]
              }
          )
      
      @task(1)
      def list_conversations(self):
          self.client.get(
              "/v1/conversations",
              headers={"Authorization": f"Bearer {self.token}"}
          )
  ```
- **Execution**: `locust -f load_test.py --users 10000 --spawn-rate 100 --host http://api.chat4all.local`

**Scenario 2: Kafka Throughput**
- **Goal**: Validate 10M messages/minute Kafka throughput
- **Tool**: Custom Python script with kafka-python
- **Script**:
  ```python
  from kafka import KafkaProducer
  import time
  import uuid
  
  producer = KafkaProducer(
      bootstrap_servers=['kafka-0:9092', 'kafka-1:9092', 'kafka-2:9092'],
      acks='all',
      compression_type='snappy'
  )
  
  start_time = time.time()
  message_count = 0
  target_rate = 166667  # 10M per minute = 166,667 per second
  
  while message_count < 10_000_000:
      producer.send(
          topic='message_processing',
          key=str(uuid.uuid4()).encode('utf-8'),
          value=b'{"content": "Test message"}'
      )
      message_count += 1
      
      # Rate limiting
      elapsed = time.time() - start_time
      expected_count = target_rate * elapsed
      if message_count > expected_count:
          time.sleep(0.001)  # 1ms delay
  
  elapsed_minutes = (time.time() - start_time) / 60
  print(f"Sent {message_count} messages in {elapsed_minutes:.2f} minutes")
  print(f"Throughput: {message_count / elapsed_minutes:.0f} msg/min")
  ```

**Scenario 3: WebSocket Concurrency**
- **Goal**: Validate 10,000 concurrent WebSocket connections per API instance
- **Tool**: Custom WebSocket client script
- **Script**:
  ```python
  import asyncio
  import websockets
  
  async def connect_websocket(url, token):
      async with websockets.connect(f"{url}?token={token}") as ws:
          # Keep connection open for 5 minutes
          await asyncio.sleep(300)
  
  async def main():
      url = "ws://api.chat4all.local/ws"
      token = "test-jwt-token"
      
      # Create 10,000 concurrent connections
      tasks = [connect_websocket(url, token) for _ in range(10000)]
      await asyncio.gather(*tasks)
  
  asyncio.run(main())
  ```

---

## R8: Observability Stack Setup

### Decision: **Prometheus + Grafana + Jaeger + Loki**

### Rationale

This is the industry-standard observability stack for Kubernetes-based distributed systems:

1. **Prometheus**: Time-series database for metrics. Native Kubernetes integration (ServiceMonitor CRD) and powerful query language (PromQL).

2. **Grafana**: Visualization layer for Prometheus metrics. Pre-built dashboards for Kubernetes, PostgreSQL, Kafka available.

3. **Jaeger**: Distributed tracing backend. Supports OpenTelemetry (OTLP) and provides trace visualization UI.

4. **Loki**: Log aggregation inspired by Prometheus (uses LogQL). Lightweight alternative to ELK stack, better Kubernetes integration.

### Implementation Pattern

**Metrics (Prometheus)**:
```python
from prometheus_client import Counter, Histogram, Gauge

# Define metrics
http_requests_total = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
http_request_duration = Histogram('http_request_duration_seconds', 'HTTP request latency', ['method', 'endpoint'])
kafka_consumer_lag = Gauge('kafka_consumer_lag', 'Kafka consumer lag', ['topic', 'group'])

# Instrument code
@app.post("/v1/messages")
async def create_message(message: MessageCreate):
    with http_request_duration.labels(method='POST', endpoint='/v1/messages').time():
        result = await message_service.create(message)
        http_requests_total.labels(method='POST', endpoint='/v1/messages', status=201).inc()
        return result
```

**Tracing (OpenTelemetry)**:
```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

# Setup tracer
trace.set_tracer_provider(TracerProvider())
jaeger_exporter = JaegerExporter(
    agent_host_name="jaeger-agent",
    agent_port=6831,
)
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(jaeger_exporter))

tracer = trace.get_tracer(__name__)

# Instrument code
@app.post("/v1/messages")
async def create_message(message: MessageCreate):
    with tracer.start_as_current_span("create_message") as span:
        span.set_attribute("conversation_id", message.conversation_id)
        result = await message_service.create(message)
        span.set_attribute("message_id", result.id)
        return result
```

**Logging (Loki)**:
```python
import logging
import json

# Structured JSON logging
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'trace_id': getattr(record, 'trace_id', None)
        }
        return json.dumps(log_data)

# Configure logger
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger('chat4all')
logger.addHandler(handler)

# Log with trace correlation
logger.info("Message created", extra={'trace_id': span.get_span_context().trace_id})
```

---

## Summary

All research tasks are complete with concrete implementation decisions:

| Research Area | Decision | Key Library/Tool |
|---------------|----------|------------------|
| OAuth 2.0 JWT | authlib for OAuth 2.0 + JWT | `authlib>=1.2.1` |
| Transactional Outbox | PostgreSQL-based with dedicated poller | SQLAlchemy ORM + custom worker |
| WebSocket Scaling | Redis Pub/Sub for fan-out | `redis-py>=5.0`, FastAPI WebSocket |
| PostgreSQL HA | Patroni with 3-node cluster (1 primary + 2 replicas) | Patroni + etcd |
| Kafka Clustering | 3-broker cluster, RF=3, min.insync.replicas=2 | kafka-python or aiokafka |
| Kubernetes Autoscaling | HPA based on CPU (70% target) | Kubernetes HPA v2 |
| Load Testing | Locust for API, custom script for Kafka | Locust + kafka-python |
| Observability | Prometheus + Grafana + Jaeger + Loki | OpenTelemetry Python SDK |

All decisions align with constitution principles and support the ≥99.95% SLA, at-least-once delivery, and <200ms p99 latency requirements.
