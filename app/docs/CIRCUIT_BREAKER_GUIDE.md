# Circuit Breaker Troubleshooting Guide

## Overview

This system implements circuit breakers for graceful degradation when Kafka or Redis become unavailable. This guide helps operators understand and troubleshoot circuit breaker behavior.

## Architecture

```
┌─────────────┐        ┌──────────────┐        ┌────────────┐
│   API       │───────>│ Circuit      │───────>│  Kafka     │
│ /v1/messages│        │ Breaker      │        │            │
└─────────────┘        └──────────────┘        └────────────┘
       │                      │ OPEN                   
       │                      ↓                         
       │               ┌──────────────┐                
       └──────────────>│ Redis Queue  │                
                       │ (Fallback)   │                
                       └──────────────┘                
                              │                         
                              ↓                         
                       ┌──────────────┐                
                       │ Backfill     │                
                       │ Worker       │                
                       └──────────────┘                
```

## Circuit Breaker States

### CLOSED (Normal Operation)
- **Behavior**: All requests pass through to Kafka/Redis
- **Monitoring**: No alerts, normal operation
- **Logs**: No circuit breaker logs

### OPEN (Service Unavailable)
- **Behavior**: All requests immediately fail without attempting service call
- **Trigger**: After `fail_max` consecutive failures
- **Duration**: Remains open for `timeout_duration` seconds
- **Kafka**: 5 failures, 60s timeout
- **Redis**: 3 failures, 30s timeout
- **Logs**: `Circuit breaker {name} opened - {service} unavailable`

### HALF-OPEN (Testing Recovery)
- **Behavior**: Next request attempts service call to test recovery
- **Success**: Circuit transitions to CLOSED
- **Failure**: Circuit returns to OPEN for another timeout period
- **Kafka**: Tests after 30s
- **Redis**: Tests after 15s
- **Logs**: `Circuit breaker {name} half-open - Testing {service} connection`

## Kafka Circuit Breaker

**Configuration** (`services/kafka_producer.py`):
```python
kafka_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=5,              # Open after 5 failures
    timeout_duration=60,     # Stay open 60 seconds
    reset_timeout=30,        # Test recovery after 30s
    name="kafka_producer"
)
```

**Failure Scenarios**:
1. Kafka broker down
2. Network timeout to Kafka
3. Kafka disk full (producer exceptions)
4. Authentication failures

**Fallback Behavior**:
- Messages queued in Redis list `fallback:message_queue`
- API returns HTTP 202 with header `X-Fallback-Mode: true`
- Backfill worker attempts republishing when circuit recovers

**Monitoring**:
```bash
# Check circuit state in logs
grep "kafka_circuit_breaker" logs/api.log

# Check fallback queue length
redis-cli LLEN fallback:message_queue

# Check backfill worker logs
docker-compose logs redis_backfill_worker
```

## Redis Circuit Breaker

**Configuration** (`services/redis_client.py`):
```python
redis_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=3,              # Open after 3 failures
    timeout_duration=30,     # Stay open 30 seconds
    reset_timeout=15,        # Test recovery after 15s
    name="redis_client"
)
```

**Protected Operations**:
- `RedisCache.get()`, `.set()`, `.delete()`
- `RateLimiter.is_allowed()`
- `MessageDeduplicator.is_duplicate()`, `.mark_seen()`

**Failure Scenarios**:
1. Redis server down
2. Network timeout
3. Redis out of memory (OOM)
4. Connection pool exhausted

**Fallback Behavior**:
- **Rate limiter**: Fails open (allows request) to avoid blocking traffic
- **Cache**: Returns `None`, proceeds without cached data
- **Deduplicator**: Returns `False` (not duplicate), allows processing

## Troubleshooting Procedures

### Scenario 1: Kafka Circuit Opens

**Symptoms**:
```
2025-12-02 10:30:00 - WARNING - Circuit breaker kafka_producer opened - Kafka unavailable
```

**Diagnosis**:
1. Check Kafka broker health:
   ```bash
   docker-compose ps kafka
   curl http://localhost:9092/health
   ```

2. Check Kafka logs:
   ```bash
   docker-compose logs kafka | tail -100
   ```

3. Check network connectivity:
   ```bash
   telnet localhost 9092
   ```

**Resolution**:
1. Restart Kafka broker:
   ```bash
   docker-compose restart kafka
   ```

2. Monitor circuit recovery:
   ```bash
   grep "kafka_producer closed\|half-open" logs/api.log
   ```

3. Verify fallback queue processing:
   ```bash
   redis-cli LLEN fallback:message_queue
   # Should decrease as backfill worker processes
   ```

### Scenario 2: Redis Circuit Opens

**Symptoms**:
```
2025-12-02 10:35:00 - WARNING - Circuit breaker redis_client opened - Redis unavailable
```

**Impact**:
- Rate limiting disabled (fail-open)
- Caching disabled
- Message deduplication disabled (potential duplicates)

**Diagnosis**:
1. Check Redis health:
   ```bash
   docker-compose ps redis
   redis-cli PING
   ```

2. Check Redis memory:
   ```bash
   redis-cli INFO memory
   ```

3. Check Redis logs:
   ```bash
   docker-compose logs redis | tail -100
   ```

**Resolution**:
1. If OOM, increase Redis max memory:
   ```yaml
   # docker-compose.yml
   redis:
     command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
   ```

2. Restart Redis:
   ```bash
   docker-compose restart redis
   ```

3. Monitor circuit recovery:
   ```bash
   grep "redis_client closed\|half-open" logs/api.log
   ```

### Scenario 3: Both Circuits Open

**Symptoms**:
```
2025-12-02 10:40:00 - ERROR - Both Kafka and Redis circuits open - cannot process message
```

**API Response**:
```
HTTP 503 Service Unavailable
{
  "detail": "Message processing services temporarily unavailable"
}
```

**Impact**:
- API rejects new messages with 503
- Existing messages in fallback queue cannot be processed
- System in degraded state

**Resolution** (Priority Order):
1. **Restore Redis first** (required for fallback queue):
   ```bash
   docker-compose restart redis
   # Wait for circuit to close
   ```

2. **Restore Kafka**:
   ```bash
   docker-compose restart kafka
   # Wait for circuit to half-open and close
   ```

3. **Verify backfill processing**:
   ```bash
   # Watch fallback queue drain
   watch -n 1 'redis-cli LLEN fallback:message_queue'
   ```

## Monitoring and Alerts

### Prometheus Metrics (Planned)

```promql
# Circuit breaker state (0=closed, 1=open, 2=half-open)
circuit_breaker_state{service="kafka"}
circuit_breaker_state{service="redis"}

# Circuit breaker failures
circuit_breaker_failures_total{service="kafka"}
circuit_breaker_failures_total{service="redis"}

# Fallback queue depth
redis_fallback_queue_length
```

### Alert Rules

```yaml
# observability/prometheus_rules.yml
- alert: KafkaCircuitBreakerOpen
  expr: circuit_breaker_state{service="kafka"} == 1
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Kafka circuit breaker open for 2 minutes"
    
- alert: RedisCircuitBreakerOpen
  expr: circuit_breaker_state{service="redis"} == 1
  for: 1m
  labels:
    severity: warning
  annotations:
    summary: "Redis circuit breaker open"

- alert: FallbackQueueBacklog
  expr: redis_fallback_queue_length > 1000
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Fallback queue has {{ $value }} messages"
```

### Log Queries

**Grafana Loki**:
```logql
# All circuit breaker events
{service="api"} |= "Circuit breaker"

# Circuit opens
{service="api"} |= "opened"

# Circuit recovery
{service="api"} |= "closed" or "half-open"

# Fallback mode activations
{service="api"} |= "X-Fallback-Mode"
```

## Load Testing Circuit Breakers

### Test 1: Kafka Failure

```bash
# Start load test
locust -f tests/load/test_api_throughput.py --host=http://localhost:8000 --users=100 --spawn-rate=10

# Kill Kafka during test
docker-compose stop kafka

# Observe:
# - Circuit opens after 5 failures
# - API continues accepting with X-Fallback-Mode: true
# - Fallback queue grows

# Restore Kafka
docker-compose start kafka

# Observe:
# - Circuit half-opens, then closes
# - Backfill worker drains queue
```

### Test 2: Redis Failure

```bash
# Start load test
locust -f tests/load/test_api_throughput.py --host=http://localhost:8000 --users=50 --spawn-rate=5

# Kill Redis during test
docker-compose stop redis

# Observe:
# - Circuit opens after 3 failures
# - Rate limiting disabled (fail-open)
# - No caching
# - Potential duplicate messages

# Restore Redis
docker-compose start redis

# Observe:
# - Circuit closes
# - Normal operation resumes
```

## Best Practices

1. **Monitor circuit breaker state**: Set up alerts for prolonged OPEN states
2. **Size fallback queue**: Ensure Redis has enough memory for peak load during Kafka outages
3. **Test regularly**: Run chaos engineering tests to validate circuit breaker behavior
4. **Document thresholds**: Adjust `fail_max` and `timeout_duration` based on your SLAs
5. **Graceful degradation**: Accept that some features (rate limiting, deduplication) may be disabled during Redis outages

## Configuration Tuning

### Aggressive (Fail Fast)
```python
# Open circuit quickly, short timeout
kafka_circuit_breaker = CircuitBreaker(
    fail_max=3,           # Open after 3 failures
    timeout_duration=30,  # 30s timeout
    reset_timeout=10      # Test after 10s
)
```

### Conservative (Tolerate Transient Errors)
```python
# More tolerant, longer recovery
kafka_circuit_breaker = CircuitBreaker(
    fail_max=10,          # Open after 10 failures
    timeout_duration=120, # 2min timeout
    reset_timeout=60      # Test after 1min
)
```

### Current Production Settings

**Kafka** (High-throughput, critical path):
- `fail_max=5`: Tolerate some failures before opening
- `timeout_duration=60s`: Allow Kafka reasonable recovery time
- `reset_timeout=30s`: Quick testing for recovery

**Redis** (Cache/rate limiter, less critical):
- `fail_max=3`: Fail faster since Redis recovery is typically quick
- `timeout_duration=30s`: Shorter timeout
- `reset_timeout=15s`: Faster recovery testing

## Related Documentation

- [services/kafka_producer.py](../services/kafka_producer.py) - Kafka circuit breaker implementation
- [services/redis_client.py](../services/redis_client.py) - Redis circuit breaker implementation
- [api/endpoints.py](../api/endpoints.py) - Fallback endpoint with circuit breaker handling
- [workers/redis_backfill.py](../workers/redis_backfill.py) - Fallback queue backfill worker
- [pybreaker documentation](https://github.com/danielfm/pybreaker) - Circuit breaker library

## Support

For issues or questions:
1. Check circuit breaker logs: `grep "Circuit breaker" logs/*.log`
2. Check service health: `docker-compose ps`
3. Check fallback queue: `redis-cli LLEN fallback:message_queue`
4. Review this guide's troubleshooting procedures
5. Escalate to on-call SRE if persistent circuit OPEN state
