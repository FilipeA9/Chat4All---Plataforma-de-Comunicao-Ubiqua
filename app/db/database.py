"""
Database connection and session management.
Provides SQLAlchemy engine, session factory, and base class.
Enhanced with production-grade connection pooling and Prometheus metrics (T105).
"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import Pool
from prometheus_client import Gauge, Counter
from core.config import settings
from core.security import hash_password

# Database connection pool metrics (T105)
db_pool_connections_active = Gauge(
    "db_pool_connections_active",
    "Number of active database connections",
    labelnames=["instance"]
)

db_pool_connections_idle = Gauge(
    "db_pool_connections_idle",
    "Number of idle database connections in pool",
    labelnames=["instance"]
)

db_pool_connections_total = Gauge(
    "db_pool_connections_total",
    "Total database connections (active + idle)",
    labelnames=["instance"]
)

db_queries_total = Counter(
    "db_queries_total",
    "Total number of database queries executed",
    labelnames=["instance"]
)

db_pool_overflows = Counter(
    "db_pool_overflows",
    "Number of times pool overflow was triggered",
    labelnames=["instance"]
)

# Production connection pool settings
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_PRE_PING = os.getenv("DB_POOL_PRE_PING", "true").lower() == "true"
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # 1 hour

# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    settings.database_url,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_pre_ping=DB_POOL_PRE_PING,
    pool_recycle=DB_POOL_RECYCLE,
    echo=settings.log_level == "DEBUG"
)

# Register pool events to track metrics (T105)
@event.listens_for(Pool, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Track database connections."""
    db_queries_total.labels(instance="api").inc()


@event.listens_for(Pool, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """Update metrics when connection is checked out from pool."""
    pool = connection_proxy._pool
    db_pool_connections_active.labels(instance="api").set(pool.checkedout())
    db_pool_connections_idle.labels(instance="api").set(pool.size() - pool.checkedout())
    db_pool_connections_total.labels(instance="api").set(pool.size())
    
    # Track overflows (connections beyond pool_size)
    if pool.overflow() > 0:
        db_pool_overflows.labels(instance="api").inc()


@event.listens_for(Pool, "checkin")
def receive_checkin(dbapi_conn, connection_record):
    """Update metrics when connection is returned to pool."""
    # Metrics will be updated on next checkout


# Create SessionLocal class for database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


def init_db() -> None:
    """
    Initialize database by creating all tables.
    Should be called once during application setup.
    """
    from db import models  # Import models to register them with Base
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")


def seed_db() -> None:
    """
    Seed database with test users.
    Creates 5 test users (user1-user5) with password 'password123'.
    """
    from db.models import User
    
    db = SessionLocal()
    try:
        # Check if users already exist
        existing_users = db.query(User).count()
        if existing_users > 0:
            print(f"Database already seeded ({existing_users} users exist)")
            return
        
        # Create 5 test users
        test_users = []
        for i in range(1, 6):
            user = User(
                username=f"user{i}",
                password=hash_password("password123")
            )
            test_users.append(user)
        
        db.add_all(test_users)
        db.commit()
        print(f"Database seeded successfully with {len(test_users)} test users")
        
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()
