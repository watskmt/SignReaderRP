from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator

from app.config import settings

# Use a synchronous engine for simplicity with FastAPI's dependency injection.
# For fully async workloads, swap to create_async_engine + AsyncSession.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,       # Detect stale connections
    pool_size=10,
    max_overflow=20,
    echo=settings.API_DEBUG,  # Log SQL when debug mode is on
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and closes it on exit."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Create all tables. Used during startup and in tests."""
    Base.metadata.create_all(bind=engine)
