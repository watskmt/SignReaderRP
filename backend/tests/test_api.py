"""
API endpoint tests for SignReader backend.
Covers both Phase 1 (main.py) and Phase 2 (main_optimized.py) endpoints.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.schemas import OCRResponse, TextResult


# ─────────────────────────────── Health ──────────────────────────────────────

def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_structure(client: TestClient) -> None:
    data = client.get("/health").json()
    assert "status" in data
    assert "version" in data
    assert "ocr_engine" in data
    assert data["status"] == "ok"
    assert data["ocr_engine"] == "paddleocr"


# ─────────────────────────────── Sessions ────────────────────────────────────

def test_create_session_success(client: TestClient) -> None:
    response = client.post(
        "/sessions",
        json={"title": "My Survey", "description": "Downtown walk"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] == "My Survey"
    assert data["status"] == "active"


def test_create_session_missing_title(client: TestClient) -> None:
    response = client.post("/sessions", json={"description": "No title here"})
    assert response.status_code == 422


def test_get_session_found(client: TestClient) -> None:
    # First create a session
    created = client.post(
        "/sessions", json={"title": "Find Me"}
    ).json()
    session_id = created["id"]

    response = client.get(f"/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json()["id"] == session_id


def test_get_session_not_found(client: TestClient) -> None:
    fake_id = str(uuid.uuid4())
    response = client.get(f"/sessions/{fake_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ─────────────────────────────── OCR (sync) ──────────────────────────────────

def test_ocr_process_valid_frame(
    client: TestClient, sample_image_b64: str
) -> None:
    """OCR endpoint returns OCRResponse shape when session exists."""
    from app.main import app as main_app, get_ocr_service

    session = client.post("/sessions", json={"title": "OCR Session"}).json()

    fixed_response = OCRResponse(
        status="success",
        texts=[TextResult(content="STOP", confidence=0.98, bounding_box=None)],
        processing_time_ms=50.0,
        engine="paddleocr",
    )
    mock_svc = MagicMock()
    mock_svc.process_frame.return_value = fixed_response
    main_app.dependency_overrides[get_ocr_service] = lambda: mock_svc

    try:
        response = client.post(
            "/ocr/process",
            json={"frame": sample_image_b64, "session_id": session["id"]},
        )
    finally:
        main_app.dependency_overrides.pop(get_ocr_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "texts" in data
    assert "processing_time_ms" in data
    assert data["engine"] == "paddleocr"


def test_ocr_process_missing_session_id(
    client: TestClient, sample_image_b64: str
) -> None:
    response = client.post("/ocr/process", json={"frame": sample_image_b64})
    assert response.status_code == 422


def test_ocr_process_missing_frame(client: TestClient) -> None:
    session = client.post("/sessions", json={"title": "S"}).json()
    response = client.post(
        "/ocr/process", json={"session_id": session["id"]}
    )
    assert response.status_code == 422


# ─────────────────────────────── OCR (async) ─────────────────────────────────

def test_ocr_process_async_returns_task_id(
    opt_client: TestClient, sample_image_b64: str
) -> None:
    session = opt_client.post("/sessions", json={"title": "Async Session"}).json()

    with patch("app.main_optimized.process_ocr_frame") as mock_task:
        mock_async_result = MagicMock()
        mock_async_result.id = "test-task-id-1234"
        mock_task.delay.return_value = mock_async_result

        response = opt_client.post(
            "/ocr/process/async",
            json={"frame": sample_image_b64, "session_id": session["id"]},
        )

    assert response.status_code == 202
    data = response.json()
    assert "task_id" in data


def test_ocr_process_async_task_structure(
    opt_client: TestClient, sample_image_b64: str
) -> None:
    session = opt_client.post("/sessions", json={"title": "Async Session 2"}).json()

    with patch("app.main_optimized.process_ocr_frame") as mock_task:
        mock_async_result = MagicMock()
        mock_async_result.id = "task-abc-xyz"
        mock_task.delay.return_value = mock_async_result

        response = opt_client.post(
            "/ocr/process/async",
            json={"frame": sample_image_b64, "session_id": session["id"]},
        )

    data = response.json()
    assert "task_id" in data
    assert "status" in data
    assert "message" in data


# ─────────────────────────────── Extractions ─────────────────────────────────

def test_save_extraction_success(client: TestClient) -> None:
    session = client.post("/sessions", json={"title": "Extract Session"}).json()

    response = client.post(
        "/extract/save",
        json={
            "session_id": session["id"],
            "content": "STOP",
            "confidence": 0.97,
            "engine": "paddleocr",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["content"] == "STOP"
    assert data["confidence"] == 0.97


def test_save_extraction_confidence_out_of_range(client: TestClient) -> None:
    session = client.post("/sessions", json={"title": "Conf Test"}).json()
    response = client.post(
        "/extract/save",
        json={
            "session_id": session["id"],
            "content": "YIELD",
            "confidence": 1.5,  # > 1.0 — invalid
            "engine": "paddleocr",
        },
    )
    assert response.status_code == 422


def test_get_extractions_returns_list(client: TestClient) -> None:
    session = client.post("/sessions", json={"title": "List Test"}).json()
    client.post(
        "/extract/save",
        json={
            "session_id": session["id"],
            "content": "NO ENTRY",
            "confidence": 0.9,
            "engine": "paddleocr",
        },
    )

    response = client.get(f"/extract/{session['id']}")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) >= 1


def test_get_extractions_empty(client: TestClient) -> None:
    session = client.post("/sessions", json={"title": "Empty"}).json()
    response = client.get(f"/extract/{session['id']}")
    assert response.status_code == 200
    assert response.json() == []


# ─────────────────────────────── Cache ───────────────────────────────────────

def test_cache_stats_structure(opt_client: TestClient) -> None:
    mock_stats = MagicMock()
    mock_stats.hit_rate = 0.75
    mock_stats.total_keys = 10
    mock_stats.memory_usage_mb = 1.5

    with patch("app.main_optimized.get_cache_service") as mock_factory:
        mock_svc = MagicMock()
        mock_svc.get_stats.return_value = mock_stats
        mock_factory.return_value = mock_svc

        response = opt_client.get("/cache/stats")

    assert response.status_code == 200
    data = response.json()
    assert "hit_rate" in data
    assert "total_keys" in data
    assert "memory_usage_mb" in data


def test_delete_cache_success(opt_client: TestClient) -> None:
    from app.main_optimized import app as opt_app, get_cache_service

    session_id = str(uuid.uuid4())
    mock_svc = MagicMock()
    opt_app.dependency_overrides[get_cache_service] = lambda: mock_svc

    try:
        response = opt_client.delete(f"/cache/{session_id}")
    finally:
        opt_app.dependency_overrides.pop(get_cache_service, None)

    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
