"""
Shared pytest fixtures for the SignReader backend test suite.
"""
from __future__ import annotations

import base64
import io
import uuid
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.database import Base, get_db
from app.models import Extraction
from app.models import Session as SessionModel
from app.models import User
from app.schemas import OCRResponse, TextResult

# ─────────────────────────────── Database setup ──────────────────────────────

SQLITE_URL = "sqlite:///./test_signreader.db"

test_engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────── Client fixture ──────────────────────────────

@pytest.fixture(scope="function")
def client() -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient that uses an in-memory SQLite database.
    Tables are created fresh for each test function.
    """
    from app.main import app

    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db

    # Patch create_tables so the lifespan startup doesn't try to connect to PostgreSQL
    with patch("app.main.create_tables"):
        with TestClient(app) as c:
            yield c

    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def opt_client() -> Generator[TestClient, None, None]:
    """
    TestClient for the optimized (Phase 2) app.
    """
    from app.main_optimized import app as opt_app

    Base.metadata.create_all(bind=test_engine)
    opt_app.dependency_overrides[get_db] = override_get_db

    # Patch create_tables so the lifespan startup doesn't try to connect to PostgreSQL
    with patch("app.main_optimized.create_tables"):
        with TestClient(opt_app) as c:
            yield c

    Base.metadata.drop_all(bind=test_engine)
    opt_app.dependency_overrides.clear()


# ─────────────────────────────── Sample data fixtures ────────────────────────

@pytest.fixture(scope="function")
def sample_user() -> Generator[User, None, None]:
    """Creates and yields a User row, then cleans up."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    user = User(
        id=str(uuid.uuid4()),
        username="testuser",
        email="testuser@example.com",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()
    db.close()


@pytest.fixture(scope="function")
def sample_session(sample_user: User) -> Generator[SessionModel, None, None]:
    """Creates and yields a Session row belonging to sample_user."""
    db = TestingSessionLocal()
    session = SessionModel(
        id=str(uuid.uuid4()),
        user_id=sample_user.id,
        title="Test Session",
        description="Created by conftest",
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    yield session
    db.close()


# ─────────────────────────────── Image fixture ───────────────────────────────

@pytest.fixture(scope="session")
def sample_image_b64() -> str:
    """100×100 white PNG encoded as a base64 string."""
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ─────────────────────────────── Mock fixtures ───────────────────────────────

@pytest.fixture(scope="function")
def mock_ocr_service() -> MagicMock:
    """MagicMock for OCRService that returns a fixed OCRResponse."""
    mock = MagicMock()
    mock.process_frame.return_value = OCRResponse(
        status="success",
        texts=[
            TextResult(
                content="STOP",
                confidence=0.98,
                bounding_box=[[10, 20], [100, 20], [100, 50], [10, 50]],
            )
        ],
        processing_time_ms=42.0,
        engine="paddleocr",
    )
    return mock


@pytest.fixture(scope="function")
def mock_redis() -> MagicMock:
    """MagicMock for the Redis client used by CacheService."""
    mock = MagicMock()
    # Default behaviours
    mock.get.return_value = None
    mock.smembers.return_value = set()
    mock.dbsize.return_value = 0
    mock.info.return_value = {"used_memory": 1024 * 1024}  # 1 MB
    mock.exists.return_value = 0
    return mock
