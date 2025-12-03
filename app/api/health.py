"""
Health check and readiness probe endpoints.
Provides liveness and readiness checks for Kubernetes and monitoring systems.
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, status, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from redis import Redis
from kafka import KafkaProducer

from api.dependencies import get_db
from core.config import settings
import os

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


def check_database(db: Session) -> Dict[str, Any]:
    """
    Check PostgreSQL database connectivity.
    
    Args:
        db: Database session
        
    Returns:
        Status dict with healthy=True/False and details
    """
    try:
        # Execute simple query to test connection
        result = db.execute(text("SELECT 1"))
        result.fetchone()
        return {"healthy": True, "message": "Database connection OK"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"healthy": False, "message": f"Database connection failed: {str(e)}"}


def check_redis() -> Dict[str, Any]:
    """
    Check Redis connectivity.
    
    Returns:
        Status dict with healthy=True/False and details
    """
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_client = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        
        # Test connection with PING
        redis_client.ping()
        redis_client.close()
        
        return {"healthy": True, "message": "Redis connection OK"}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"healthy": False, "message": f"Redis connection failed: {str(e)}"}


def check_kafka() -> Dict[str, Any]:
    """
    Check Kafka connectivity.
    
    Returns:
        Status dict with healthy=True/False and details
    """
    try:
        kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        
        # Create producer with short timeout
        producer = KafkaProducer(
            bootstrap_servers=kafka_servers.split(","),
            request_timeout_ms=2000,
            api_version_auto_timeout_ms=2000
        )
        
        # Get cluster metadata (validates connection)
        producer.bootstrap_connected()
        producer.close()
        
        return {"healthy": True, "message": "Kafka connection OK"}
    except Exception as e:
        logger.error(f"Kafka health check failed: {e}")
        return {"healthy": False, "message": f"Kafka connection failed: {str(e)}"}


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Liveness probe endpoint.
    
    Returns basic service status without checking dependencies.
    Used by Kubernetes liveness probes to determine if pod should be restarted.
    
    Returns:
        Service status and version
        
    Example Response:
        {
            "status": "healthy",
            "service": "Chat4All API",
            "version": "2.0.0"
        }
    """
    return {
        "status": "healthy",
        "service": "Chat4All API",
        "version": "2.0.0",
        "environment": os.getenv("ENVIRONMENT", "development")
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness probe endpoint.
    
    Checks connectivity to all critical dependencies (PostgreSQL, Redis, Kafka).
    Used by Kubernetes readiness probes to determine if pod can receive traffic.
    Returns 200 OK only if all dependencies are healthy, 503 otherwise.
    
    Args:
        db: Database session (injected)
        
    Returns:
        Detailed health status of all dependencies
        
    Raises:
        HTTPException: 503 Service Unavailable if any dependency is unhealthy
        
    Example Response (all healthy):
        {
            "status": "ready",
            "checks": {
                "database": {"healthy": true, "message": "Database connection OK"},
                "redis": {"healthy": true, "message": "Redis connection OK"},
                "kafka": {"healthy": true, "message": "Kafka connection OK"}
            }
        }
        
    Example Response (degraded):
        {
            "status": "not_ready",
            "checks": {
                "database": {"healthy": true, "message": "Database connection OK"},
                "redis": {"healthy": false, "message": "Redis connection failed: Connection refused"},
                "kafka": {"healthy": true, "message": "Kafka connection OK"}
            }
        }
    """
    checks = {
        "database": check_database(db),
        "redis": check_redis(),
        "kafka": check_kafka()
    }
    
    # Determine overall readiness
    all_healthy = all(check["healthy"] for check in checks.values())
    
    if all_healthy:
        return {
            "status": "ready",
            "checks": checks
        }
    else:
        # Log which services are unhealthy
        unhealthy_services = [
            service for service, check in checks.items() 
            if not check["healthy"]
        ]
        logger.warning(f"Readiness check failed for services: {', '.join(unhealthy_services)}")
        
        # Return 503 Service Unavailable
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "checks": checks
            }
        )


@router.get("/metrics/basic", status_code=status.HTTP_200_OK)
async def basic_metrics(db: Session = Depends(get_db)):
    """
    Basic application metrics endpoint (non-Prometheus format).
    
    Returns simple JSON metrics for quick monitoring.
    Full Prometheus metrics available at /metrics.
    
    Args:
        db: Database session (injected)
        
    Returns:
        Basic metrics including database connection pool status
        
    Example Response:
        {
            "database": {
                "pool_size": 20,
                "checked_out_connections": 5,
                "overflow": 2
            },
            "service": {
                "uptime_seconds": 3600,
                "version": "2.0.0"
            }
        }
    """
    try:
        from db.database import engine
        pool = engine.pool
        
        return {
            "database": {
                "pool_size": pool.size(),
                "checked_out_connections": pool.checkedout(),
                "overflow": pool.overflow(),
                "checked_in_connections": pool.checkedin()
            },
            "service": {
                "version": "2.0.0",
                "environment": os.getenv("ENVIRONMENT", "development")
            }
        }
    except Exception as e:
        logger.error(f"Failed to collect basic metrics: {e}")
        return {
            "error": "Failed to collect metrics",
            "service": {
                "version": "2.0.0",
                "environment": os.getenv("ENVIRONMENT", "development")
            }
        }
