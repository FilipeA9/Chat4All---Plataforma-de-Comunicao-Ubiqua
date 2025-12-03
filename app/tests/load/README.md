# Load Testing Suite

Comprehensive load tests for the Chat4All platform using Locust.

## Overview

This directory contains load tests to validate the platform's performance under various scenarios:
- **API throughput**: 10M messages/minute
- **WebSocket connections**: 10K concurrent connections
- **File uploads**: 100 concurrent 1GB uploads

## Quick Start - Execute All Tests (T131)

Run the complete load testing suite to validate all NFR targets:

**Linux/macOS**:
```bash
chmod +x run_all_tests.sh
./run_all_tests.sh
```

**Windows (PowerShell)**:
```powershell
.\run_all_tests.ps1
```

This will execute:
1. API Throughput Test (5 minutes, 1000 users)
2. WebSocket Scalability Test (5 minutes, 5000 users)
3. File Upload Test (10 minutes, 100 users)
4. Sustained Throughput Test (15 minutes, 2000 users)

**Total Duration**: ~45 minutes (including cooldown periods)

**Reports Location**: `tests/load/reports/<timestamp>/`
- HTML reports: `*.html`
- CSV data: `*.csv`
- Logs: `*.log`
- Summary: `summary.txt`

**Analyze Results**:
```bash
python analyze_results.py tests/load/reports/<timestamp>
```

## Prerequisites

```bash
# Install dependencies
pip install locust websocket-client

# Ensure services are running
docker-compose up -d

# Verify API is healthy
curl http://localhost:8000/health
```

## Test Scenarios

### 1. API Throughput Test (`test_api_throughput.py`)

**Objective**: Validate API can handle 10M messages/minute (166K msg/s)

**What it tests**:
- POST /v1/messages throughput
- Authentication overhead
- Read endpoints (GET /v1/conversations)
- Latency percentiles (p50, p95, p99)

**Usage**:
```bash
# Web UI (interactive)
locust -f test_api_throughput.py --host=http://localhost:8000

# Headless (automated)
locust -f test_api_throughput.py --host=http://localhost:8000 \
       --users=1000 --spawn-rate=100 --run-time=5m --headless

# With CSV reports
locust -f test_api_throughput.py --host=http://localhost:8000 \
       --users=1000 --spawn-rate=100 --run-time=5m --headless \
       --csv=reports/api_throughput
```

**Expected Results**:
```
Throughput: ~166,000 msg/min
p99 Latency: <200ms
Success Rate: >99%
```

**Troubleshooting**:
- If throughput is low, check Kafka lag: `kafka-consumer-groups --describe`
- If latency is high, check database pool: `curl localhost:8000/metrics | grep db_pool`
- If errors occur, check logs: `docker-compose logs api`

### 2. WebSocket Connections Test (`test_websocket_connections.py`)

**Objective**: Validate system can maintain 10K concurrent WebSocket connections with <100ms notification latency

**What it tests**:
- WebSocket connection establishment
- Authentication with JWT
- Subscription to conversations
- Heartbeat/ping-pong mechanism
- Real-time notification delivery latency

**Usage**:
```bash
# Small test (100 connections)
locust -f test_websocket_connections.py --host=ws://localhost:8000 \
       --users=100 --spawn-rate=10 --run-time=2m

# Full scale test (10K connections)
locust -f test_websocket_connections.py --host=ws://localhost:8000 \
       --users=10000 --spawn-rate=1000 --run-time=10m --headless

# Distributed (for >10K connections)
# Master node
locust -f test_websocket_connections.py --host=ws://localhost:8000 \
       --master --expect-workers=4

# Worker nodes (run on 4 different machines)
locust -f test_websocket_connections.py --worker --master-host=<master-ip>
```

**Expected Results**:
```
Concurrent Connections: 10,000
Connection Success Rate: >99%
Notification p99 Latency: <100ms
CPU Usage: <70%
```

**Troubleshooting**:
- If connections fail, check Redis Pub/Sub: `redis-cli CLIENT LIST`
- If latency is high, check Redis connection pool
- If CPU is high, scale API instances: `docker-compose up -d --scale api=3`

### 3. File Upload Test (`test_file_upload.py`)

**Objective**: Validate chunked upload performance with 100 concurrent 1GB uploads

**What it tests**:
- POST /v1/files/initiate (upload session creation)
- POST /v1/files/{id}/chunks (chunk upload)
- POST /v1/files/{id}/complete (merge trigger)
- Chunk upload latency (<5s per 10MB)
- MinIO storage performance

**Usage**:
```bash
# Small test (10 uploads)
locust -f test_file_upload.py --host=http://localhost:8000 \
       --users=10 --spawn-rate=2 --run-time=5m

# Full scale test (100 uploads)
locust -f test_file_upload.py --host=http://localhost:8000 \
       --users=100 --spawn-rate=10 --run-time=10m --headless

# Report slow chunks
locust -f test_file_upload.py --host=http://localhost:8000 \
       --users=100 --spawn-rate=10 --run-time=10m --headless \
       --csv=reports/file_upload | grep "Slow Chunks"
```

**Expected Results**:
```
Concurrent Uploads: 100
Avg Chunk Upload Time: <5s (10MB chunks)
Success Rate: >99%
Throughput: >200 MB/s aggregate
```

**Troubleshooting**:
- If chunk upload is slow, check MinIO: `mc admin info local`
- If merge fails, check worker logs: `docker-compose logs file_merge_worker`
- If disk is full, check MinIO storage: `mc du local/chat4all-files`

## Running All Tests

```bash
#!/bin/bash
# run_all_load_tests.sh

echo "Starting Load Test Suite..."

# Test 1: API Throughput
echo "Test 1/3: API Throughput (5 minutes)..."
locust -f test_api_throughput.py --host=http://localhost:8000 \
       --users=1000 --spawn-rate=100 --run-time=5m --headless \
       --csv=reports/api_throughput

sleep 30  # Cooldown

# Test 2: WebSocket Connections
echo "Test 2/3: WebSocket Connections (5 minutes)..."
locust -f test_websocket_connections.py --host=ws://localhost:8000 \
       --users=1000 --spawn-rate=100 --run-time=5m --headless \
       --csv=reports/websocket

sleep 30  # Cooldown

# Test 3: File Upload
echo "Test 3/3: File Upload (5 minutes)..."
locust -f test_file_upload.py --host=http://localhost:8000 \
       --users=50 --spawn-rate=10 --run-time=5m --headless \
       --csv=reports/file_upload

echo "Load tests complete! Check reports/ directory."
```

## Interpreting Results

### Locust Web UI

Access http://localhost:8089 when running with web UI:
- **Charts**: Real-time request rate, response time, user count
- **Statistics**: Per-endpoint metrics, percentiles, failures
- **Failures**: Detailed error messages and counts
- **Download Data**: Export CSV/Excel for analysis

### Command-Line Output

```
Type     Name                          # reqs      # fails   Avg     Min     Max   Median  p95    p99   req/s failures/s
--------|------------------------------|-----------|---------|-------|-------|-------|--------|------|------|------|----------
POST     /v1/messages                  100000      50        120     45      2340  110     250    450   1666.67  0.83
GET      /v1/conversations             10000       5         80      30      1200  70      150    300   166.67   0.08
```

**Key Metrics**:
- **# reqs**: Total requests sent
- **# fails**: Failed requests (target: <1%)
- **Avg**: Average response time (target: <200ms for API, <100ms for WS)
- **p99**: 99th percentile latency (worst-case user experience)
- **req/s**: Requests per second (throughput)
- **failures/s**: Failure rate

### CSV Reports

Generated with `--csv=reports/prefix`:
- `prefix_stats.csv`: Aggregate statistics
- `prefix_stats_history.csv`: Time-series data (for graphs)
- `prefix_failures.csv`: Detailed failure information

**Analyze with Python/pandas**:
```python
import pandas as pd

# Load statistics
stats = pd.read_csv('reports/api_throughput_stats.csv')

# Filter high-latency requests
slow_requests = stats[stats['95%'] > 200]
print(slow_requests[['Name', '95%', '99%']])

# Load history for time-series analysis
history = pd.read_csv('reports/api_throughput_stats_history.csv')
history['Timestamp'] = pd.to_datetime(history['Timestamp'], unit='s')

# Plot throughput over time
import matplotlib.pyplot as plt
history.plot(x='Timestamp', y='Requests/s', figsize=(12, 6))
plt.title('API Throughput Over Time')
plt.ylabel('Requests per Second')
plt.show()
```

## Monitoring During Load Tests

### Prometheus Metrics

```bash
# API request rate
curl -s localhost:9090/api/v1/query?query=rate\(http_requests_total\[1m\]\) | jq

# Kafka consumer lag
curl -s localhost:9090/api/v1/query?query=kafka_consumer_lag | jq

# Database pool utilization
curl -s localhost:9090/api/v1/query?query=db_pool_connections_active | jq

# WebSocket connections
curl -s localhost:9090/api/v1/query?query=websocket_connections_active | jq
```

### Grafana Dashboards

Access http://localhost:3000 (admin/admin):
- **API Health**: Request rate, latency, error rate
- **Message Pipeline**: Kafka lag, worker throughput
- **Database Performance**: Query latency, pool utilization
- **WebSocket**: Connection count, notification latency

### Live Logs

```bash
# API logs
docker-compose logs -f api | grep ERROR

# Worker logs
docker-compose logs -f message_router | grep WARN

# Kafka logs
docker-compose logs -f kafka | grep ERROR

# Database logs
docker-compose logs -f postgres | grep ERROR
```

### System Resources

```bash
# Docker stats
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Host resources
top -b -n 1 | head -20
```

## Performance Targets Summary

| Metric | Target | Test |
|--------|--------|------|
| API Throughput | 10M msg/min (166K msg/s) | test_api_throughput.py |
| API p99 Latency | <200ms | test_api_throughput.py |
| WebSocket Connections | 10K concurrent | test_websocket_connections.py |
| WS Notification Latency | <100ms p99 | test_websocket_connections.py |
| File Upload Concurrency | 100 users | test_file_upload.py |
| Chunk Upload Time | <5s per 10MB | test_file_upload.py |
| Success Rate | >99% | All tests |

## Troubleshooting Common Issues

### "Connection Refused" Errors

```bash
# Check services are running
docker-compose ps

# Check API health
curl http://localhost:8000/health

# Check logs
docker-compose logs api | tail -50
```

### High Latency

**Symptoms**: p99 latency >200ms

**Diagnosis**:
1. Check database pool exhaustion:
   ```bash
   curl localhost:8000/metrics | grep db_pool_connections_active
   ```

2. Check Kafka lag:
   ```bash
   kafka-consumer-groups --bootstrap-server localhost:9092 --describe --all-groups
   ```

3. Check Redis memory:
   ```bash
   redis-cli INFO memory
   ```

**Solutions**:
- Scale API instances: `docker-compose up -d --scale api=3`
- Increase DB pool: Edit `db/database.py`, set `pool_size=50`
- Scale workers: `docker-compose up -d --scale message_router=10`

### High Failure Rate

**Symptoms**: >5% failed requests

**Diagnosis**:
1. Check error responses:
   ```bash
   docker-compose logs api | grep "HTTP 5"
   ```

2. Check authentication failures:
   ```bash
   docker-compose logs api | grep "401\|403"
   ```

3. Check database connectivity:
   ```bash
   docker-compose exec api python -c "from db.database import get_db; next(get_db()); print('OK')"
   ```

**Solutions**:
- If 401 errors, increase token expiration: `ACCESS_TOKEN_EXPIRE_MINUTES=30`
- If 503 errors, check service health endpoints
- If 500 errors, review application logs for exceptions

### Locust Master/Worker Connection Issues

**Symptoms**: Workers can't connect to master

**Solution**:
```bash
# On master
locust -f test.py --master --master-bind-host=0.0.0.0 --master-bind-port=5557

# On workers
locust -f test.py --worker --master-host=<master-ip> --master-port=5557
```

## Best Practices

1. **Start Small**: Test with 10-100 users before scaling to thousands
2. **Ramp Gradually**: Use `--spawn-rate` to avoid overwhelming the system
3. **Monitor**: Watch Grafana dashboards and Prometheus metrics during tests
4. **Cooldown**: Wait 30-60s between tests to allow metrics to stabilize
5. **Baseline**: Run tests on idle system first to establish baseline
6. **Document**: Save CSV reports and screenshots for comparison
7. **Iterate**: Identify bottlenecks, optimize, re-test

## Related Documentation

- [../workers/README.md](../workers/README.md) - Worker architecture and scaling
- [../docs/CIRCUIT_BREAKER_GUIDE.md](../docs/CIRCUIT_BREAKER_GUIDE.md) - Resilience patterns
- [../../specs/002-production-ready/spec.md](../../specs/002-production-ready/spec.md) - NFR requirements
- [Locust Documentation](https://docs.locust.io/) - Official Locust docs

## Support

For issues or questions:
1. Check this README's troubleshooting section
2. Review Grafana dashboards for bottlenecks
3. Check Prometheus metrics for anomalies
4. Search Jaeger for slow trace_ids
5. Review system logs: `docker-compose logs`
6. Escalate to performance engineering team
