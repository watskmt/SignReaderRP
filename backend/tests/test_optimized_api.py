"""
Unit tests for Phase 2 optimized API endpoints (main_optimized.py).
Covers session stats, filters, export, and task status endpoints.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ─────────────────────────────── Session Stats ───────────────────────────────

class TestSessionStats:
    def test_stats_returns_correct_counts(self, opt_client: TestClient) -> None:
        from app.main_optimized import app as opt_app, get_filter_service

        session = opt_client.post("/sessions", json={"title": "Stats Test"}).json()

        mock_filter = MagicMock()
        mock_filter.is_duplicate.return_value = False
        opt_app.dependency_overrides[get_filter_service] = lambda: mock_filter

        try:
            opt_client.post(
                "/extract/save",
                json={
                    "session_id": session["id"],
                    "content": "STOP",
                    "confidence": 0.95,
                    "engine": "paddleocr",
                },
            )
            opt_client.post(
                "/extract/save",
                json={
                    "session_id": session["id"],
                    "content": "STOP",
                    "confidence": 0.90,
                    "engine": "paddleocr",
                },
            )
            opt_client.post(
                "/extract/save",
                json={
                    "session_id": session["id"],
                    "content": "YIELD",
                    "confidence": 0.88,
                    "engine": "paddleocr",
                },
            )

            response = opt_client.get(f"/sessions/{session['id']}/stats")
        finally:
            opt_app.dependency_overrides.pop(get_filter_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session["id"]
        assert data["total_extractions"] == 3
        assert data["unique_texts"] >= 1
        assert data["avg_confidence"] > 0

    def test_stats_empty_session(self, opt_client: TestClient) -> None:
        session = opt_client.post("/sessions", json={"title": "Empty Stats"}).json()

        response = opt_client.get(f"/sessions/{session['id']}/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_extractions"] == 0
        assert data["unique_texts"] == 0
        assert data["avg_confidence"] == 0.0

    def test_stats_session_not_found(self, opt_client: TestClient) -> None:
        fake_id = str(uuid.uuid4())
        response = opt_client.get(f"/sessions/{fake_id}/stats")
        assert response.status_code == 404


# ─────────────────────────────── Filters ─────────────────────────────────────

class TestFilterEndpoints:
    def test_set_keywords(self, opt_client: TestClient) -> None:
        from app.main_optimized import app as opt_app, get_filter_service

        mock_filter = MagicMock()
        opt_app.dependency_overrides[get_filter_service] = lambda: mock_filter

        try:
            response = opt_client.post(
                "/filters/keywords",
                json={
                    "session_id": "session-1",
                    "keywords": ["STOP", "YIELD"],
                    "mode": "include",
                },
            )
        finally:
            opt_app.dependency_overrides.pop(get_filter_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["session_id"] == "session-1"
        assert data["keywords"] == ["STOP", "YIELD"]
        mock_filter.set_keywords.assert_called_once_with(
            "session-1", ["STOP", "YIELD"], "include"
        )

    def test_get_keywords(self, opt_client: TestClient) -> None:
        from app.main_optimized import app as opt_app, get_filter_service

        from app.schemas import FilterConfig

        mock_filter = MagicMock()
        mock_filter.get_keywords.return_value = FilterConfig(
            session_id="session-1",
            keywords=["EXIT"],
            mode="exclude",
        )
        opt_app.dependency_overrides[get_filter_service] = lambda: mock_filter

        try:
            response = opt_client.get("/filters/keywords/session-1")
        finally:
            opt_app.dependency_overrides.pop(get_filter_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "session-1"
        assert data["keywords"] == ["EXIT"]
        assert data["mode"] == "exclude"


# ─────────────────────────────── Export ──────────────────────────────────────

class TestExportSession:
    def test_export_returns_full_payload(self, opt_client: TestClient) -> None:
        from app.main_optimized import app as opt_app, get_filter_service

        session = opt_client.post(
            "/sessions", json={"title": "Export Me", "description": "For testing"}
        ).json()

        mock_filter = MagicMock()
        mock_filter.is_duplicate.return_value = False
        opt_app.dependency_overrides[get_filter_service] = lambda: mock_filter

        try:
            opt_client.post(
                "/extract/save",
                json={
                    "session_id": session["id"],
                    "content": "STOP",
                    "confidence": 0.95,
                    "engine": "paddleocr",
                },
            )
            response = opt_client.get(f"/export/{session['id']}")
        finally:
            opt_app.dependency_overrides.pop(get_filter_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["session"]["title"] == "Export Me"
        assert data["session"]["description"] == "For testing"
        assert data["session"]["ended_at"] is None
        assert data["total_extractions"] >= 1
        assert len(data["extractions"]) >= 1
        assert data["extractions"][0]["content"] == "STOP"

    def test_export_session_not_found(self, opt_client: TestClient) -> None:
        fake_id = str(uuid.uuid4())
        response = opt_client.get(f"/export/{fake_id}")
        assert response.status_code == 404

    def test_export_with_bounding_box(self, opt_client: TestClient) -> None:
        from app.main_optimized import app as opt_app, get_filter_service

        session = opt_client.post("/sessions", json={"title": "Box Export"}).json()

        mock_filter = MagicMock()
        mock_filter.is_duplicate.return_value = False
        opt_app.dependency_overrides[get_filter_service] = lambda: mock_filter

        bbox = [[0, 0], [100, 0], [100, 20], [0, 20]]

        try:
            opt_client.post(
                "/extract/save",
                json={
                    "session_id": session["id"],
                    "content": "SPEED LIMIT",
                    "confidence": 0.92,
                    "bounding_box": bbox,
                    "engine": "paddleocr",
                },
            )
            response = opt_client.get(f"/export/{session['id']}")
        finally:
            opt_app.dependency_overrides.pop(get_filter_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["extractions"][0]["bounding_box"] == bbox


# ─────────────────────────────── Task Status ─────────────────────────────────

class TestTaskStatus:
    def test_pending_task(self, opt_client: TestClient) -> None:
        with patch("app.main_optimized.AsyncResult") as mock_result:
            mock_instance = MagicMock()
            mock_instance.state = "PENDING"
            mock_result.return_value = mock_instance

            response = opt_client.get("/tasks/task-pending-123")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-pending-123"
        assert data["status"] == "pending"

    def test_success_task(self, opt_client: TestClient) -> None:
        with patch("app.main_optimized.AsyncResult") as mock_result:
            mock_instance = MagicMock()
            mock_instance.state = "SUCCESS"
            mock_instance.result = {"status": "success", "texts_saved": 2}
            mock_result.return_value = mock_instance

            response = opt_client.get("/tasks/task-success-456")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["result"]["texts_saved"] == 2

    def test_failure_task(self, opt_client: TestClient) -> None:
        with patch("app.main_optimized.AsyncResult") as mock_result:
            mock_instance = MagicMock()
            mock_instance.state = "FAILURE"
            mock_instance.info = Exception("OCR engine crashed")
            mock_result.return_value = mock_instance

            response = opt_client.get("/tasks/task-fail-789")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failure"
        assert "OCR engine crashed" in data["error"]

    def test_unknown_state(self, opt_client: TestClient) -> None:
        with patch("app.main_optimized.AsyncResult") as mock_result:
            mock_instance = MagicMock()
            mock_instance.state = "RETRY"
            mock_result.return_value = mock_instance

            response = opt_client.get("/tasks/task-retry-000")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "retry"


# ─────────────────────────────── Sync OCR with Session Not Found ─────────────

class TestSyncOcrEdgeCases:
    def test_process_ocr_session_not_found(
        self, opt_client: TestClient, sample_image_b64: str
    ) -> None:
        fake_id = str(uuid.uuid4())
        response = opt_client.post(
            "/ocr/process",
            json={"frame": sample_image_b64, "session_id": fake_id},
        )
        assert response.status_code == 404

    def test_process_ocr_invalid_base64(self, opt_client: TestClient) -> None:
        from app.main_optimized import app as opt_app, get_ocr_service, get_filter_service

        session = opt_client.post("/sessions", json={"title": "OCR Bad Frame"}).json()

        mock_ocr = MagicMock()
        mock_ocr.process_frame.side_effect = ValueError("Invalid base64 data")
        mock_filter = MagicMock()

        opt_app.dependency_overrides[get_ocr_service] = lambda: mock_ocr
        opt_app.dependency_overrides[get_filter_service] = lambda: mock_filter

        try:
            response = opt_client.post(
                "/ocr/process",
                json={"frame": "!!!invalid-base64!!!", "session_id": session["id"]},
            )
        finally:
            opt_app.dependency_overrides.pop(get_ocr_service, None)
            opt_app.dependency_overrides.pop(get_filter_service, None)

        assert response.status_code == 400


# ─────────────────────────────── Async OCR Session Not Found ─────────────────

class TestAsyncOcrEdgeCases:
    def test_process_ocr_async_session_not_found(
        self, opt_client: TestClient, sample_image_b64: str
    ) -> None:
        fake_id = str(uuid.uuid4())

        with patch("app.main_optimized.process_ocr_frame") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-123")

            response = opt_client.post(
                "/ocr/process/async",
                json={"frame": sample_image_b64, "session_id": fake_id},
            )

        assert response.status_code == 404


# ─────────────────────────────── Cache Endpoints ─────────────────────────────

class TestCacheEndpoints:
    def test_clear_cache(self, opt_client: TestClient) -> None:
        from app.main_optimized import app as opt_app, get_cache_service

        mock_cache = MagicMock()
        opt_app.dependency_overrides[get_cache_service] = lambda: mock_cache

        try:
            response = opt_client.delete("/cache/session-to-clear")
        finally:
            opt_app.dependency_overrides.pop(get_cache_service, None)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "session-to-clear" in data["message"]
        mock_cache.clear_all_session_data.assert_called_once_with("session-to-clear")


# ─────────────────────────────── Extraction with Bounding Box ────────────────

class TestExtractionEdgeCases:
    def test_save_extraction_with_bounding_box(self, opt_client: TestClient) -> None:
        from app.main_optimized import app as opt_app, get_filter_service

        session = opt_client.post("/sessions", json={"title": "Box Test"}).json()

        mock_filter = MagicMock()
        mock_filter.is_duplicate.return_value = False
        opt_app.dependency_overrides[get_filter_service] = lambda: mock_filter

        bbox = [[10, 20], [100, 20], [100, 50], [10, 50]]

        try:
            response = opt_client.post(
                "/extract/save",
                json={
                    "session_id": session["id"],
                    "content": "ONE WAY",
                    "confidence": 0.91,
                    "bounding_box": bbox,
                    "latitude": 35.6762,
                    "longitude": 139.6503,
                    "engine": "paddleocr",
                },
            )
        finally:
            opt_app.dependency_overrides.pop(get_filter_service, None)

        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "ONE WAY"
        assert data["bounding_box"] == bbox
        assert data["latitude"] == 35.6762
        assert data["longitude"] == 139.6503
        assert data["is_duplicate"] is False

    def test_list_extractions_with_bounding_box(self, opt_client: TestClient) -> None:
        from app.main_optimized import app as opt_app, get_filter_service

        session = opt_client.post("/sessions", json={"title": "List Box Test"}).json()

        mock_filter = MagicMock()
        mock_filter.is_duplicate.return_value = False
        opt_app.dependency_overrides[get_filter_service] = lambda: mock_filter

        bbox = [[0, 0], [50, 0], [50, 20], [0, 20]]

        try:
            opt_client.post(
                "/extract/save",
                json={
                    "session_id": session["id"],
                    "content": "NO PARKING",
                    "confidence": 0.87,
                    "bounding_box": bbox,
                    "engine": "paddleocr",
                },
            )
            response = opt_client.get(f"/extract/{session['id']}")
        finally:
            opt_app.dependency_overrides.pop(get_filter_service, None)

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["bounding_box"] == bbox

    def test_save_extraction_session_not_found(self, opt_client: TestClient) -> None:
        from app.main_optimized import app as opt_app, get_filter_service

        mock_filter = MagicMock()
        opt_app.dependency_overrides[get_filter_service] = lambda: mock_filter

        try:
            response = opt_client.post(
                "/extract/save",
                json={
                    "session_id": str(uuid.uuid4()),
                    "content": "STOP",
                    "confidence": 0.95,
                    "engine": "paddleocr",
                },
            )
        finally:
            opt_app.dependency_overrides.pop(get_filter_service, None)

        assert response.status_code == 404

    def test_list_extractions_empty(self, opt_client: TestClient) -> None:
        session = opt_client.post("/sessions", json={"title": "Empty List"}).json()
        response = opt_client.get(f"/extract/{session['id']}")
        assert response.status_code == 200
        assert response.json() == []
