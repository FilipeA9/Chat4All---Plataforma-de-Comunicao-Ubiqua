"""
Database connection and session management.
Provides SQLAlchemy engine, session factory, and base class.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import settings
from core.security import hash_password

# Create SQLAlchemy engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=settings.log_level == "DEBUG"
)

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
                password_hash=hash_password("password123"),
                full_name=f"Test User {i}"
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
