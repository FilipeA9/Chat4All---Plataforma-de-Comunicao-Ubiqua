# Kafka High Availability Cluster - Production Guide

This document describes the **Kafka HA cluster** implementation for **Chat4All**, designed for **zero-downtime operation** and **zero data loss** under single-broker failures.

## Architecture Overview

### Cluster Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    Kafka HA Cluster (3 brokers)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐      │
│  │  Kafka-1     │   │  Kafka-2     │   │  Kafka-3     │      │
│  │  Port: 9092  │   │  Port: 9093  │   │  Port: 9094  │      │
│  │  Broker ID: 1│   │  Broker ID: 2│   │  Broker ID: 3│      │
│  │  JMX: 9999   │   │  JMX: 9999   │   │  JMX: 9999   │      │
│  └──────────────┘   └──────────────┘   └──────────────┘      │
│          │                  │                  │               │
│          └──────────────────┴──────────────────┘               │
│                            │                                    │
│  ┌─────────────────────────────────────────────────────┐      │
│  │         ZooKeeper Ensemble (Quorum: 3 nodes)        │      │
│  ├─────────────────────────────────────────────────────┤      │
│  │  ZK-1:2181  │  ZK-2:2182  │  ZK-3:2183             │      │
│  └─────────────────────────────────────────────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      Monitoring Stack                           │
├─────────────────────────────────────────────────────────────────┤
│  Kafka UI (port 8080)                                           │
│  Kafka Health Monitor (port 9090) ─► Prometheus Metrics        │
└─────────────────────────────────────────────────────────────────┘
```

### Data Replication

- **Replication Factor (RF)**: 3 (all partitions replicated to all 3 brokers)
- **Min In-Sync Replicas (min.insync.replicas)**: 2 (write succeeds if ≥2 replicas acknowledge)
- **Producer ACKs**: `all` (wait for all in-sync replicas)
- **Idempotency**: Enabled (exactly-once delivery)

### Failure Tolerance

| Scenario | Behavior | Data Loss | Downtime |
|----------|----------|-----------|----------|
| 1 broker fails | Continue operating on 2 brokers | ❌ None | ❌ None |
| 2 brokers fail | System unavailable (min.insync=2) | ❌ None | ✅ Until 1 broker recovers |
| 3 brokers fail | Complete outage | ❌ None (data persisted) | ✅ Until 1 broker recovers |
| 1 ZooKeeper fails | Continue with 2-node quorum | ❌ None | ❌ None |
| 2 ZooKeepers fail | System unavailable (quorum lost) | ❌ None | ✅ Until ZK quorum restored |

**Key Property**: The system can survive **any single broker failure** with **zero data loss** and **zero downtime**.

---

## Quick Start

### 1. Start Kafka HA Cluster

```bash
# Start 3 brokers + 3 ZooKeeper nodes + health monitor
docker-compose -f docker-compose.kafka-cluster.yml up -d

# Wait for all services to be healthy (~60 seconds)
docker-compose -f docker-compose.kafka-cluster.yml ps

# Check logs
docker-compose -f docker-compose.kafka-cluster.yml logs -f kafka-1
```

### 2. Verify Cluster Health

**Option A: Kafka UI (Web Interface)**
```
Open browser: http://localhost:8080

Navigate to:
- Brokers tab → Should show 3 brokers online
- Topics tab → Should show all topics with RF=3
- Consumers tab → Monitor consumer lag
```

**Option B: Prometheus Metrics**
```bash
# Check health monitor metrics
curl http://localhost:9090/metrics | grep kafka_

# Expected metrics:
# kafka_cluster_brokers 3.0
# kafka_under_replicated_partitions{topic="__total__"} 0.0
# kafka_offline_partitions{topic="messages"} 0.0
# kafka_broker_online{broker_id="1",host="kafka-1",port="29092"} 1.0
```

**Option C: Command Line**
```bash
# List brokers
docker exec kafka-1 kafka-broker-api-versions --bootstrap-server kafka-1:29092

# Describe topics (check replication)
docker exec kafka-1 kafka-topics \
  --bootstrap-server kafka-1:29092 \
  --describe --topic messages

# Expected output:
# Topic: messages   PartitionCount: 100   ReplicationFactor: 3
# Partition: 0   Leader: 1   Replicas: 1,2,3   Isr: 1,2,3
```

### 3. Update Application Configuration

```bash
# Update .env to point to 3 brokers
KAFKA_BOOTSTRAP_SERVERS=kafka-1:9092,kafka-2:9093,kafka-3:9094

# Restart application
docker-compose restart
```

---

## Failover Testing

### Test 1: Single Broker Failure

**Scenario**: Kill broker-1 while system is under load

```bash
# Terminal 1: Monitor metrics
watch -n 1 'curl -s http://localhost:9090/metrics | grep kafka_cluster_brokers'

# Terminal 2: Kill broker-1
docker stop kafka-1

# Expected behavior:
# - kafka_cluster_brokers drops to 2.0
# - kafka_under_replicated_partitions increases (some partitions now RF=2)
# - Producers continue publishing (min.insync=2 satisfied)
# - Consumers continue consuming (leader election for affected partitions)
# - No messages lost

# Wait 30 seconds, check logs
docker-compose -f docker-compose.kafka-cluster.yml logs kafka-health-monitor

# Expected log:
# WARNING - Kafka cluster degraded: only 2/3 brokers available
# WARNING - Kafka cluster has X under-replicated partitions

# Restart broker-1
docker start kafka-1

# Wait 60 seconds for catch-up
# kafka_under_replicated_partitions should return to 0.0
```

**Validation**:
```bash
# Check ISR (In-Sync Replicas) for a partition
docker exec kafka-2 kafka-topics \
  --bootstrap-server kafka-2:29092 \
  --describe --topic messages \
  --partition 0

# Before failure: Isr: 1,2,3
# During failure: Isr: 2,3
# After recovery: Isr: 1,2,3
```

### Test 2: Network Partition

**Scenario**: Simulate network partition between broker-1 and ZooKeeper

```bash
# Stop ZooKeeper connection for broker-1 (simulated)
docker network disconnect chat4all-network kafka-1

# Expected behavior:
# - Broker-1 detects ZooKeeper connection loss
# - Other brokers detect broker-1 offline
# - Partitions led by broker-1 elect new leader (broker-2 or broker-3)
# - Producers/consumers switch to new leaders automatically
# - kafka_broker_online{broker_id="1"} = 0.0

# Restore network
docker network connect chat4all-network kafka-1

# Broker-1 rejoins cluster and syncs data
```

### Test 3: Leader Election

**Scenario**: Force leader re-election by stopping the leader broker

```bash
# Find current leader for partition 0
LEADER=$(docker exec kafka-1 kafka-topics \
  --bootstrap-server kafka-1:29092 \
  --describe --topic messages \
  --partition 0 | grep Leader | awk '{print $6}')

echo "Current leader for messages-0: Broker $LEADER"

# Stop the leader broker
docker stop kafka-$LEADER

# Check new leader (should be different broker)
sleep 10
NEW_LEADER=$(docker exec kafka-1 kafka-topics \
  --bootstrap-server kafka-2:29092 \
  --describe --topic messages \
  --partition 0 | grep Leader | awk '{print $6}')

echo "New leader for messages-0: Broker $NEW_LEADER"

# Restart original leader
docker start kafka-$LEADER
```

**Expected Result**: Leader election completes in **<5 seconds**, no message loss.

---

## Monitoring & Alerting

### Prometheus Metrics

The **kafka-health-monitor** exports these metrics every 30 seconds:

| Metric | Type | Description | Alert Threshold |
|--------|------|-------------|-----------------|
| `kafka_cluster_brokers` | Gauge | Number of online brokers | < 3 (degraded) |
| `kafka_broker_online{broker_id}` | Gauge | Broker availability (1=online) | 0 (offline) |
| `kafka_under_replicated_partitions{topic}` | Gauge | Partitions with ISR < RF | > 0 (data at risk) |
| `kafka_offline_partitions{topic}` | Gauge | Partitions with no leader | > 0 (unavailable) |
| `kafka_isr_shrink_events{topic,partition}` | Counter | ISR shrink events (replica lag) | Rate > 0.1/min |
| `kafka_cluster_topics` | Gauge | Total topics in cluster | - |

### Prometheus Alert Rules

Add to `observability/prometheus_rules.yml`:

```yaml
groups:
  - name: kafka_ha_alerts
    interval: 30s
    rules:
      # Broker offline alert
      - alert: KafkaBrokerOffline
        expr: kafka_broker_online == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Kafka broker {{ $labels.broker_id }} is offline"
          description: "Broker {{ $labels.broker_id }} ({{ $labels.host }}:{{ $labels.port }}) has been offline for >1 minute"

      # Cluster degraded alert
      - alert: KafkaClusterDegraded
        expr: kafka_cluster_brokers < 3
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Kafka cluster is degraded ({{ $value }}/3 brokers online)"
          description: "Kafka cluster has been running with fewer than 3 brokers for >2 minutes. Data replication may be affected."

      # Under-replicated partitions alert
      - alert: KafkaUnderReplicatedPartitions
        expr: kafka_under_replicated_partitions{topic!="__total__"} > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Topic {{ $labels.topic }} has {{ $value }} under-replicated partitions"
          description: "Some partitions are not fully replicated. Risk of data loss if another broker fails."

      # Offline partitions alert (critical)
      - alert: KafkaOfflinePartitions
        expr: kafka_offline_partitions{topic!="__total__"} > 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "Topic {{ $labels.topic }} has {{ $value }} offline partitions"
          description: "CRITICAL: Some partitions have no leader. Data is unavailable for produce/consume operations."

      # ISR shrink rate alert
      - alert: KafkaISRShrinkRateHigh
        expr: rate(kafka_isr_shrink_events[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High ISR shrink rate for topic {{ $labels.topic }}"
          description: "Replicas are frequently falling out of sync. Check broker performance, disk I/O, network latency."
```

### Grafana Dashboard

Import dashboard JSON or create panels:

```json
{
  "dashboard": {
    "title": "Kafka HA Cluster",
    "panels": [
      {
        "title": "Broker Availability",
        "targets": [
          {"expr": "kafka_cluster_brokers", "legendFormat": "Online Brokers"}
        ],
        "alert": {"conditions": [{"evaluator": {"params": [3], "type": "lt"}}]}
      },
      {
        "title": "Under-Replicated Partitions",
        "targets": [
          {"expr": "kafka_under_replicated_partitions{topic='__total__'}"}
        ]
      },
      {
        "title": "ISR Shrink Events (Rate)",
        "targets": [
          {"expr": "rate(kafka_isr_shrink_events[5m])"}
        ]
      }
    ]
  }
}
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka-1:9092,...` | Comma-separated broker list |
| `KAFKA_HEALTH_CHECK_INTERVAL` | `30` | Health check interval (seconds) |
| `ENABLE_KAFKA_HEALTH_MONITORING` | `true` | Enable/disable monitoring |
| `METRICS_PORT` | `9090` | Prometheus metrics port |

### Topic Configuration

| Topic | Partitions | Replication Factor | min.insync.replicas |
|-------|------------|-------------------|---------------------|
| `messages` | 100 | 3 | 2 |
| `file_merge_requests` | 50 | 3 | 2 |
| `message_status_updates` | 50 | 3 | 2 |
| `dlq` | 3 | 3 | 2 |

### Broker Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| `default.replication.factor` | 3 | All data replicated 3 times |
| `min.insync.replicas` | 2 | Write succeeds if ≥2 replicas ack |
| `unclean.leader.election.enable` | false | Prevent data loss on leader election |
| `log.retention.hours` | 168 (7 days) | Retain logs for 1 week |
| `log.segment.bytes` | 1GB | Segment size for log compaction |
| `compression.type` | producer | Use producer-side compression |

---

## Troubleshooting

### Issue: Under-Replicated Partitions Won't Clear

**Symptoms**:
- `kafka_under_replicated_partitions > 0` for >10 minutes
- Broker logs show replication lag

**Diagnosis**:
```bash
# Check replication lag per broker
docker exec kafka-1 kafka-replica-verification \
  --broker-list kafka-1:29092,kafka-2:29092,kafka-3:29092 \
  --topic-white-list '.*'

# Check disk space
docker exec kafka-1 df -h /var/lib/kafka/data

# Check broker JMX metrics
curl http://localhost:9999/metrics | grep UnderReplicatedPartitions
```

**Solutions**:
1. **Increase `replica.lag.time.max.ms`** if network is slow
2. **Increase disk I/O** (faster storage, increase buffer sizes)
3. **Reduce producer throughput** temporarily
4. **Check broker CPU/memory** usage

### Issue: Broker Stuck in "Starting" State

**Symptoms**:
- `docker-compose ps` shows broker unhealthy
- Health check fails repeatedly

**Diagnosis**:
```bash
# Check broker logs
docker logs kafka-1 --tail 100

# Common errors:
# - "Timed out waiting for connection to ZooKeeper" → ZK not ready
# - "FATAL [KafkaServer id=1] Fatal error during startup" → config issue
# - "OutOfMemoryError" → increase KAFKA_HEAP_OPTS
```

**Solutions**:
1. **ZooKeeper not ready**: Wait for ZK quorum (check `zookeeper-1` logs)
2. **Port conflict**: Check `netstat -tuln | grep 9092`
3. **Memory**: Increase `KAFKA_HEAP_OPTS=-Xmx2G -Xms2G`

### Issue: High ISR Shrink Rate

**Symptoms**:
- `kafka_isr_shrink_events` counter increasing rapidly
- Replicas frequently fall out of sync

**Diagnosis**:
```bash
# Check broker metrics
docker exec kafka-1 kafka-run-class kafka.tools.JmxTool \
  --object-name kafka.server:type=ReplicaManager,name=IsrShrinksPerSec \
  --jmx-url service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi

# Check network latency between brokers
docker exec kafka-1 ping kafka-2 -c 10
```

**Root Causes**:
1. **Network latency** between brokers
2. **Disk I/O bottleneck** (slow writes)
3. **Producer burst traffic** (replicas can't keep up)

**Solutions**:
1. Increase `replica.fetch.max.bytes` and `replica.socket.timeout.ms`
2. Enable log compression (`compression.type=snappy`)
3. Add more broker resources (CPU, disk IOPS)

---

## Performance Tuning

### Producer Optimization

```python
# services/kafka_producer.py
producer = KafkaProducer(
    bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
    acks='all',  # Wait for all in-sync replicas (slower but safer)
    retries=5,
    max_in_flight_requests_per_connection=5,
    enable_idempotence=True,
    compression_type='snappy',  # Enable compression
    linger_ms=10,  # Batch messages for 10ms (reduces network calls)
    batch_size=32768,  # 32KB batch size
    buffer_memory=67108864  # 64MB buffer
)
```

### Consumer Optimization

```python
# workers/message_router.py
consumer = KafkaConsumer(
    'messages',
    bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
    group_id='message-router-group',
    auto_offset_reset='earliest',
    enable_auto_commit=False,  # Manual commit for exactly-once
    max_poll_records=500,  # Process 500 messages per poll
    fetch_min_bytes=10240,  # Wait for 10KB before returning
    fetch_max_wait_ms=500  # Max wait 500ms
)
```

### Broker Tuning

Add to `docker-compose.kafka-cluster.yml`:

```yaml
environment:
  # Thread configuration
  KAFKA_NUM_NETWORK_THREADS: 8
  KAFKA_NUM_IO_THREADS: 8
  KAFKA_NUM_REPLICA_FETCHERS: 4
  
  # Buffer sizes
  KAFKA_SOCKET_SEND_BUFFER_BYTES: 1048576  # 1MB
  KAFKA_SOCKET_RECEIVE_BUFFER_BYTES: 1048576
  KAFKA_SOCKET_REQUEST_MAX_BYTES: 104857600  # 100MB
  
  # Log configuration
  KAFKA_LOG_FLUSH_INTERVAL_MESSAGES: 10000
  KAFKA_LOG_FLUSH_INTERVAL_MS: 1000
  KAFKA_LOG_RETENTION_CHECK_INTERVAL_MS: 300000
  
  # Compression
  KAFKA_COMPRESSION_TYPE: snappy
```

---

## Migration from Single-Broker to HA Cluster

### Step 1: Backup Existing Data

```bash
# Backup topics configuration
docker exec kafka-single kafka-topics \
  --bootstrap-server localhost:9092 \
  --describe > topics_backup.txt

# Backup consumer offsets
docker exec kafka-single kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --all-groups --describe > offsets_backup.txt
```

### Step 2: Start HA Cluster

```bash
# Start 3-broker cluster on different ports
docker-compose -f docker-compose.kafka-cluster.yml up -d
```

### Step 3: Mirror Topics (Zero-Downtime)

```bash
# Use MirrorMaker 2 to replicate data
docker run --rm --network chat4all-network \
  confluentinc/cp-kafka:7.5.0 \
  kafka-mirror-maker \
  --consumer.config /tmp/consumer.properties \
  --producer.config /tmp/producer.properties \
  --whitelist '.*'

# consumer.properties:
# bootstrap.servers=kafka-single:9092
# group.id=mirrormaker

# producer.properties:
# bootstrap.servers=kafka-1:29092,kafka-2:29092,kafka-3:29092
```

### Step 4: Switch Application

```bash
# Update .env
KAFKA_BOOTSTRAP_SERVERS=kafka-1:9092,kafka-2:9093,kafka-3:9094

# Rolling restart (zero downtime)
docker-compose restart api-1
sleep 10
docker-compose restart api-2
```

### Step 5: Verify & Decommission

```bash
# Verify consumer lag (should be 0)
docker exec kafka-1 kafka-consumer-groups \
  --bootstrap-server kafka-1:29092 \
  --group message-router-group \
  --describe

# Stop old single-broker Kafka
docker stop kafka-single
```

---

## Best Practices

1. **Always use 3+ brokers** in production (enables RF=3)
2. **Monitor under-replicated partitions** daily (should be 0)
3. **Set `min.insync.replicas=2`** to prevent data loss
4. **Enable producer idempotency** for exactly-once delivery
5. **Test failover quarterly** (kill random broker, verify recovery)
6. **Size disk for 7-day retention** minimum (168 hours)
7. **Use dedicated ZooKeeper ensemble** (don't share with other services)
8. **Enable JMX metrics** for advanced monitoring
9. **Compress messages** (snappy or lz4) to reduce disk/network usage
10. **Document partition key strategy** (ensures even distribution)

---

## References

- **Kafka Documentation**: https://kafka.apache.org/documentation/
- **Replication Design**: https://kafka.apache.org/documentation/#replication
- **Production Configuration**: https://kafka.apache.org/documentation/#configuration
- **Confluent Best Practices**: https://docs.confluent.io/platform/current/kafka/deployment.html

---

**Implementation**: T049-T052 (Phase 4: Zero-Downtime Infrastructure)  
**Status**: ✅ Production-Ready  
**Last Updated**: 2025-01-27
