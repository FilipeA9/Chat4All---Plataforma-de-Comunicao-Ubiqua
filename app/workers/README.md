# Workers Documentation

This directory contains background workers that process asynchronous tasks for the Chat4All platform.

## Overview

Workers consume messages from Kafka topics and perform various operations:
- Message routing to external channels (WhatsApp, Instagram)
- File chunk merging for large uploads
- Outbox event publishing for transactional guarantees
- Fallback queue processing for graceful degradation
- Garbage collection for abandoned uploads

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Kafka     │────>│   Workers    │────>│   External      │
│   Topics    │     │              │     │   Services      │
└─────────────┘     └──────────────┘     └─────────────────┘
                           │
                           ↓
                    ┌──────────────┐
                    │  PostgreSQL  │
                    │  MinIO       │
                    │  Redis       │
                    └──────────────┘
```

## Workers

### 1. Message Router (`message_router.py`)

**Purpose**: Route messages to external channels (WhatsApp, Instagram)

**Kafka Topics**:
- Consumes: `message_processing`
- Produces: `message_status_updates`, `message_processing_dlq` (on failure)

**Key Features**:
- Message deduplication (24-hour window)
- Retry logic with exponential backoff (3 attempts)
- Dead Letter Queue for failed messages
- Channel-specific routing (WhatsApp, Instagram, all)
- Distributed tracing with OpenTelemetry

**Configuration**:
```bash
# Environment variables
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_CONSUMER_GROUP=message_router_group
KAFKA_AUTO_OFFSET_RESET=earliest
```

**Usage**:
```bash
# Run single instance
python -m workers.message_router

# Run with Docker Compose (5 replicas for parallelism)
docker-compose up -d --scale message_router=5
```

**Monitoring**:
```bash
# Check consumer lag
kafka-consumer-groups --bootstrap-server kafka:9092 --group message_router_group --describe

# Check Prometheus metrics
curl http://localhost:8000/metrics | grep message_processing
```

### 2. Outbox Poller (`outbox_poller.py`)

**Purpose**: Poll unpublished outbox events and publish to Kafka (Transactional Outbox pattern)

**Database Tables**:
- Reads: `outbox_events` (WHERE published=FALSE)
- Updates: `outbox_events.published`, `outbox_events.published_at`

**Key Features**:
- Polling interval: 500ms
- Atomic DB transaction (SELECT FOR UPDATE)
- Exponential backoff on failures (1s, 2s, 4s)
- Max 3 retries per event
- Publishes to Redis Pub/Sub for real-time notifications

**Configuration**:
```bash
# Environment variables
OUTBOX_POLL_INTERVAL_MS=500
OUTBOX_MAX_RETRIES=3
OUTBOX_BATCH_SIZE=100
```

**Usage**:
```bash
# Run single instance (only 1 needed due to DB locking)
python -m workers.outbox_poller

# Run with Docker Compose
docker-compose up -d outbox_poller
```

**Monitoring**:
```bash
# Check pending events
psql -h localhost -U chat4all -d chat4all_db -c "SELECT COUNT(*) FROM outbox_events WHERE published=FALSE;"

# Check Prometheus metrics
curl http://localhost:8000/metrics | grep outbox
```

### 3. Redis Backfill Worker (`redis_backfill.py`)

**Purpose**: Process fallback queue when Kafka circuit breaker opens

**Redis Keys**:
- Reads: `fallback:message_queue` (LPOP)
- Writes: `fallback:message_queue` (RPUSH on retry)

**Key Features**:
- Polling interval: 10s
- Batch processing (50 messages/batch)
- Atomic LPOP operations
- Respects circuit breaker state
- Re-queues on failure for retry

**Configuration**:
```bash
# Environment variables
REDIS_URL=redis://redis:6379/0
FALLBACK_POLL_INTERVAL=10
FALLBACK_BATCH_SIZE=50
```

**Usage**:
```bash
# Run single instance
python -m workers.redis_backfill

# Run with Docker Compose
docker-compose up -d redis_backfill
```

**Monitoring**:
```bash
# Check fallback queue length
redis-cli LLEN fallback:message_queue

# Check worker logs
docker-compose logs -f redis_backfill
```

### 4. File Merge Worker (`file_merge_worker.py`)

**Purpose**: Merge uploaded file chunks into final file

**Kafka Topics**:
- Consumes: `file_merge_requests`

**Key Features**:
- Retrieves chunks from MinIO
- Uses MinIO compose_object for server-side merge
- Updates file status to COMPLETED
- Cleans up chunk objects after merge
- Generates presigned download URL

**Configuration**:
```bash
# Environment variables
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=chat4all-files
```

**Usage**:
```bash
# Run single instance
python -m workers.file_merge_worker

# Run with Docker Compose (3 replicas for parallelism)
docker-compose up -d --scale file_merge_worker=3
```

**Monitoring**:
```bash
# Check pending file merges
psql -h localhost -U chat4all -d chat4all_db -c "SELECT COUNT(*) FROM files WHERE status='MERGING';"

# Check MinIO objects
mc ls local/chat4all-files/chunks/
```

### 5. Upload Garbage Collector (`upload_garbage_collector.py`)

**Purpose**: Clean up abandoned file uploads (>24 hours old)

**Schedule**: Daily at 2 AM (Kubernetes CronJob)

**Key Features**:
- Finds uploads with status=UPLOADING AND created_at < NOW() - 24h
- Deletes chunk objects from MinIO
- Deletes file_chunks records from database
- Updates file status to FAILED
- Metrics for cleanup operations

**Configuration**:
```bash
# Environment variables
GC_RETENTION_HOURS=24
GC_BATCH_SIZE=100
```

**Usage**:
```bash
# Run manually
python -m workers.upload_garbage_collector

# Run with Kubernetes CronJob (see k8s/cronjobs.yaml)
kubectl apply -f k8s/cronjobs/upload-gc.yaml
```

**Monitoring**:
```bash
# Check abandoned uploads
psql -h localhost -U chat4all -d chat4all_db -c "SELECT COUNT(*) FROM files WHERE status='UPLOADING' AND created_at < NOW() - INTERVAL '24 hours';"

# Check Prometheus metrics
curl http://localhost:8000/metrics | grep uploads_cleaned
```

### 6. Mock Workers (Development Only)

**WhatsApp Mock** (`whatsapp_mock.py`):
- Simulates WhatsApp Business API
- Consumes from `message_processing`
- Publishes to `message_status_updates`

**Instagram Mock** (`instagram_mock.py`):
- Simulates Instagram Messaging API
- Consumes from `message_processing`
- Publishes to `message_status_updates`

**Usage**:
```bash
# Run in development
docker-compose up -d whatsapp_mock instagram_mock

# Disable in production (comment out in docker-compose.yml)
```

## Deployment

### Docker Compose (Development)

```yaml
# docker-compose.yml
services:
  message_router:
    build: .
    command: python -m workers.message_router
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    deploy:
      replicas: 5  # Parallel processing
  
  outbox_poller:
    build: .
    command: python -m workers.outbox_poller
    environment:
      - DATABASE_URL=postgresql://chat4all:password@postgres:5432/chat4all_db
    deploy:
      replicas: 1  # Single instance (DB locking)
  
  redis_backfill:
    build: .
    command: python -m workers.redis_backfill
    environment:
      - REDIS_URL=redis://redis:6379/0
    deploy:
      replicas: 1  # Single instance
```

### Kubernetes (Production)

```yaml
# k8s/worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: message-router
spec:
  replicas: 10
  selector:
    matchLabels:
      app: message-router
  template:
    metadata:
      labels:
        app: message-router
    spec:
      containers:
      - name: message-router
        image: chat4all:latest
        command: ["python", "-m", "workers.message_router"]
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
```

## Monitoring and Observability

### Prometheus Metrics

All workers expose metrics on `/metrics`:

```promql
# Message processing rate
rate(messages_processed_total[5m])

# Worker processing latency
histogram_quantile(0.99, rate(worker_processing_duration_seconds_bucket[5m]))

# Dead Letter Queue additions
rate(dlq_messages_total[5m])

# Outbox pending events
outbox_pending_events

# Fallback queue depth
redis_fallback_queue_length
```

### OpenTelemetry Tracing

Workers propagate trace context from Kafka headers:

```python
# Extract trace context from Kafka message headers
context = extract_trace_context(kafka_message.headers())

# Continue span in worker
with tracer.start_as_current_span("process_message", context=context):
    # Worker processing logic
    pass
```

**Jaeger UI**: http://localhost:16686

### Logging

Structured JSON logs with mandatory fields:

```json
{
  "timestamp": "2025-12-02T10:30:00.123Z",
  "level": "INFO",
  "service": "message_router",
  "trace_id": "abc123def456",
  "message": "Message processed successfully",
  "user_id": 123,
  "conversation_id": 456,
  "message_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Loki Query**: http://localhost:3000 (Grafana)

```logql
{service="message_router"} |= "trace_id"
```

## Troubleshooting

### Worker Not Processing Messages

**Check 1: Kafka Consumer Lag**
```bash
kafka-consumer-groups --bootstrap-server kafka:9092 --group message_router_group --describe
```

**Check 2: Worker Logs**
```bash
docker-compose logs -f message_router
```

**Check 3: Dead Letter Queue**
```bash
kafka-console-consumer --bootstrap-server kafka:9092 --topic message_processing_dlq --from-beginning
```

### Outbox Events Not Publishing

**Check 1: Pending Events**
```sql
SELECT COUNT(*), MIN(created_at), MAX(created_at) 
FROM outbox_events 
WHERE published=FALSE;
```

**Check 2: Outbox Poller Running**
```bash
docker-compose ps outbox_poller
docker-compose logs outbox_poller | tail -50
```

**Check 3: Kafka Connectivity**
```bash
docker-compose exec outbox_poller python -c "from kafka import KafkaProducer; p = KafkaProducer(bootstrap_servers='kafka:9092'); print('OK')"
```

### Fallback Queue Growing

**Check 1: Queue Length**
```bash
redis-cli LLEN fallback:message_queue
```

**Check 2: Backfill Worker Running**
```bash
docker-compose ps redis_backfill
docker-compose logs redis_backfill | tail -50
```

**Check 3: Kafka Circuit Breaker State**
```bash
grep "kafka_circuit_breaker" logs/api.log | tail -10
```

**Resolution**: Restore Kafka service, circuit will close, backfill worker will drain queue

### File Merge Failures

**Check 1: Pending Merges**
```sql
SELECT id, filename, total_chunks, uploaded_chunks, status 
FROM files 
WHERE status='MERGING' 
ORDER BY created_at DESC 
LIMIT 10;
```

**Check 2: MinIO Chunks**
```bash
mc ls local/chat4all-files/chunks/{upload_id}/
```

**Check 3: Worker Logs**
```bash
docker-compose logs file_merge_worker | grep ERROR
```

## Performance Tuning

### Message Router Scaling

```yaml
# Increase replicas for higher throughput
docker-compose up -d --scale message_router=20

# Kubernetes HPA
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: message-router-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: message-router
  minReplicas: 5
  maxReplicas: 50
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### Kafka Consumer Configuration

```python
# Increase throughput
consumer = KafkaConsumer(
    'message_processing',
    bootstrap_servers='kafka:9092',
    max_poll_records=500,        # Process 500 msgs per poll
    fetch_min_bytes=1048576,     # Wait for 1MB before returning
    fetch_max_wait_ms=500,       # Or wait max 500ms
    enable_auto_commit=False,    # Manual commit for exactly-once
)
```

### Outbox Poller Optimization

```python
# Increase batch size for higher throughput
OUTBOX_BATCH_SIZE = 500  # Process 500 events per iteration

# Reduce polling interval for lower latency
OUTBOX_POLL_INTERVAL_MS = 100  # Poll every 100ms
```

## Development

### Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export DATABASE_URL=postgresql://chat4all:password@localhost:5432/chat4all_db
export REDIS_URL=redis://localhost:6379/0

# Run worker
python -m workers.message_router
```

### Testing

```bash
# Unit tests
pytest tests/test_workers.py

# Integration tests
pytest tests/integration/test_message_ordering.py

# Load tests
locust -f tests/load/worker_load_test.py
```

## Related Documentation

- [../docs/CIRCUIT_BREAKER_GUIDE.md](../docs/CIRCUIT_BREAKER_GUIDE.md) - Circuit breaker troubleshooting
- [../services/README.md](../services/README.md) - Service layer documentation
- [../api/README.md](../api/README.md) - API documentation
- [../specs/002-production-ready/](../specs/002-production-ready/) - Design specifications

## Support

For issues or questions:
1. Check worker logs: `docker-compose logs {worker_name}`
2. Check Kafka consumer lag
3. Check Prometheus metrics
4. Review this guide's troubleshooting section
5. Search Jaeger for trace_id if available
6. Escalate to development team
