"""
Kafka Health Monitor Worker (T052).

Periodically collects Kafka cluster metadata and updates Prometheus metrics:
- Broker online status
- Under-replicated partitions
- Offline partitions
- ISR shrink events

This enables alerting on:
- Broker failures (kafka_broker_online == 0)
- Data loss risk (kafka_under_replicated_partitions > 0)
- Service unavailability (kafka_offline_partitions > 0)

Usage:
    python -m workers.kafka_health_monitor

Environment Variables:
    KAFKA_HEALTH_CHECK_INTERVAL: Seconds between health checks (default: 30)
    ENABLE_KAFKA_HEALTH_MONITORING: Enable monitoring (default: true)
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Dict, Set

from core.config import settings
from services.kafka_producer import get_kafka_producer
from workers.metrics import update_kafka_broker_health

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
HEALTH_CHECK_INTERVAL = int(os.getenv('KAFKA_HEALTH_CHECK_INTERVAL', '30'))
ENABLE_MONITORING = os.getenv('ENABLE_KAFKA_HEALTH_MONITORING', 'true').lower() == 'true'

# ISR tracking for detecting shrink events
isr_state: Dict[str, Dict[int, Set[int]]] = {}  # {topic: {partition: set(replica_ids)}}


def detect_isr_shrink(metadata: dict) -> None:
    """
    Detect ISR (In-Sync Replicas) shrink events.
    
    ISR shrink occurs when a replica falls behind and is removed from ISR.
    This indicates:
    - Broker slow/unavailable
    - Network issues
    - Disk I/O problems
    
    Args:
        metadata: Cluster metadata with partition details
    """
    global isr_state
    
    topics = metadata.get('topics', {})
    
    for topic_name, topic_info in topics.items():
        if topic_name not in isr_state:
            isr_state[topic_name] = {}
        
        for partition in topic_info.get('partition_details', []):
            partition_id = partition['partition']
            current_isr = set(partition.get('isr', []))
            
            # Check if we have previous ISR state
            if partition_id in isr_state[topic_name]:
                previous_isr = isr_state[topic_name][partition_id]
                
                # ISR shrink: current ISR smaller than previous
                if len(current_isr) < len(previous_isr):
                    removed_replicas = previous_isr - current_isr
                    logger.warning(
                        f"ISR shrink detected: topic={topic_name} "
                        f"partition={partition_id} "
                        f"removed_replicas={removed_replicas} "
                        f"isr={current_isr}"
                    )
                    # Increment counter for each shrink event
                    from workers.metrics import kafka_isr_shrink_events
                    kafka_isr_shrink_events.labels(
                        topic=topic_name,
                        partition=str(partition_id)
                    ).inc()
            
            # Update ISR state
            isr_state[topic_name][partition_id] = current_isr


async def monitor_kafka_health():
    """
    Main monitoring loop for Kafka cluster health.
    
    Collects cluster metadata every HEALTH_CHECK_INTERVAL seconds and:
    1. Updates Prometheus metrics
    2. Detects ISR shrink events
    3. Logs critical issues (offline brokers, offline partitions)
    """
    logger.info(
        f"Kafka health monitor started "
        f"(interval={HEALTH_CHECK_INTERVAL}s, enabled={ENABLE_MONITORING})"
    )
    
    if not ENABLE_MONITORING:
        logger.info("Kafka health monitoring is disabled")
        return
    
    kafka_producer = get_kafka_producer()
    consecutive_failures = 0
    max_consecutive_failures = 5
    
    while True:
        try:
            # Fetch cluster metadata
            metadata = kafka_producer.get_cluster_metadata()
            
            # Update Prometheus metrics
            update_kafka_broker_health(metadata)
            
            # Detect ISR shrink events
            detect_isr_shrink(metadata)
            
            # Log warnings for critical issues
            broker_count = metadata.get('broker_count', 0)
            under_replicated = metadata.get('under_replicated_partitions', 0)
            
            if broker_count < 3:
                logger.warning(
                    f"Kafka cluster degraded: only {broker_count}/3 brokers available"
                )
            
            if under_replicated > 0:
                logger.warning(
                    f"Kafka cluster has {under_replicated} under-replicated partitions"
                )
            
            # Check for offline partitions
            topics = metadata.get('topics', {})
            for topic_name, topic_info in topics.items():
                offline_count = sum(
                    1 for p in topic_info.get('partition_details', [])
                    if p.get('leader') is None
                )
                if offline_count > 0:
                    logger.error(
                        f"CRITICAL: Topic {topic_name} has {offline_count} offline partitions"
                    )
            
            # Reset failure counter on success
            consecutive_failures = 0
            
            # Log success (at debug level to avoid spam)
            logger.debug(
                f"Health check successful: {broker_count} brokers, "
                f"{metadata.get('topic_count', 0)} topics, "
                f"{under_replicated} under-replicated partitions"
            )
        
        except Exception as e:
            consecutive_failures += 1
            logger.error(
                f"Failed to collect Kafka health metrics "
                f"(attempt {consecutive_failures}/{max_consecutive_failures}): {e}"
            )
            
            if consecutive_failures >= max_consecutive_failures:
                logger.critical(
                    f"Kafka health monitoring failed {max_consecutive_failures} times, "
                    f"restarting monitor..."
                )
                # Set all broker metrics to 0 (unknown state)
                from workers.metrics import kafka_cluster_brokers
                kafka_cluster_brokers.set(0)
                
                # Reset failure counter to retry
                consecutive_failures = 0
        
        # Wait for next check
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)


def shutdown_handler(signum, frame):
    """Handle graceful shutdown on SIGINT/SIGTERM."""
    logger.info(f"Received signal {signum}, shutting down Kafka health monitor...")
    sys.exit(0)


def main():
    """Run Kafka health monitor."""
    # Register signal handlers
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    logger.info("Starting Kafka Health Monitor (T052)")
    logger.info(f"Kafka brokers: {settings.kafka_bootstrap_servers}")
    logger.info(f"Check interval: {HEALTH_CHECK_INTERVAL}s")
    
    # Run monitoring loop
    try:
        asyncio.run(monitor_kafka_health())
    except KeyboardInterrupt:
        logger.info("Kafka health monitor stopped by user")
    except Exception as e:
        logger.exception(f"Kafka health monitor failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
