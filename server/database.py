"""
Database configuration and session management.

Uses SQLAlchemy with PostgreSQL on Railway.
"""

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from .logging_config import logger

# Get DATABASE_URL from Railway environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.warning(
        "⚠️ DATABASE_URL not set - falling back to SQLite (not recommended for production)"
    )
    DATABASE_URL = "sqlite:///./data/openpoke.db"
else:
    # Railway uses postgres:// but SQLAlchemy 2.0 requires postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        logger.info("✅ Using PostgreSQL database from Railway")

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=5,  # Number of connections to maintain
    max_overflow=10,  # Additional connections when pool is full
    echo=False,  # Set to True to log SQL queries (debug mode)
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency that provides a database session.

    Usage in FastAPI:
    ```python
    @router.get("/users")
    def get_users(db: Session = Depends(get_db)):
        return db.query(User).all()
    ```

    Yields:
        Session: SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database tables.

    Creates all tables defined in models if they don't exist.
    Call this on application startup.
    """
    try:
        # Import all models here to ensure they're registered with Base
        from .db_models import User  # noqa: F401

        # Create all tables
        Base.metadata.create_all(bind=engine)

        logger.info("✅ Database initialized successfully")
    except Exception as exc:
        logger.error(f"❌ Database initialization failed: {exc}")
        raise


def check_db_connection() -> bool:
    """
    Check if database connection is working.

    Returns:
        bool: True if connection successful, False otherwise
    """
    try:
        from sqlalchemy import text

        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("✅ Database connection verified")
        return True
    except Exception as exc:
        logger.error(f"❌ Database connection failed: {exc}")
        return False


__all__ = ["engine", "SessionLocal", "Base", "get_db", "init_db", "check_db_connection"]
