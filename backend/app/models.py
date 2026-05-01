import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    username = Column(String(100), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=_now)

    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username}>"


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active")
    started_at = Column(DateTime, nullable=False, default=_now)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_now)
    updated_at = Column(DateTime, nullable=False, default=_now, onupdate=_now)

    user = relationship("User", back_populates="sessions")
    extractions = relationship(
        "Extraction", back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_sessions_status", "status"),
        Index("ix_sessions_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<Session id={self.id} title={self.title} status={self.status}>"


class Extraction(Base):
    __tablename__ = "extractions"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    content = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    bounding_box = Column(Text, nullable=True)  # JSON-serialised list of points
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=_now)
    engine = Column(String(50), nullable=False, default="paddleocr")
    is_duplicate = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=_now)

    session = relationship("Session", back_populates="extractions")

    __table_args__ = (
        Index("ix_extractions_session_id", "session_id"),
        Index("ix_extractions_session_duplicate", "session_id", "is_duplicate"),
    )

    def __repr__(self) -> str:
        return (
            f"<Extraction id={self.id} content={self.content[:30]!r} "
            f"confidence={self.confidence:.2f}>"
        )
