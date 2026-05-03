"""
Unit tests for Celery tasks in app.tasks.
Database and external services are mocked.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.schemas import OCRResponse, TextResult


# ─────────────────────────────── Helpers ─────────────────────────────────────

def _make_mock_ocr_response(texts: List[tuple]) -> OCRResponse:
    """Create an OCRResponse from [(content, confidence), ...]."""
    return OCRResponse(
        status="success",
        texts=[
            TextResult(content=text, confidence=conf, bounding_box=None)
            for text, conf in texts
        ],
        processing_time_ms=50.0,
        engine="paddleocr",
    )


def _make_mock_session(session_id: str = "test-session-id") -> MagicMock:
    """Create a mock Session object."""
    session = MagicMock()
    session.id = session_id
    session.title = "Test Session"
    session.description = "Test description"
    session.status = "active"
    session.started_at = datetime.utcnow()
    session.ended_at = None
    return session


def _make_mock_extraction(extraction_id: str = "test-ext-id", **kwargs) -> MagicMock:
    """Create a mock Extraction object."""
    ext = MagicMock()
    ext.id = extraction_id
    ext.session_id = kwargs.get("session_id", "test-session-id")
    ext.content = kwargs.get("content", "STOP")
    ext.confidence = kwargs.get("confidence", 0.95)
    ext.bounding_box = kwargs.get("bounding_box")
    ext.latitude = kwargs.get("latitude")
    ext.longitude = kwargs.get("longitude")
    ext.altitude = kwargs.get("altitude")
    ext.timestamp = kwargs.get("timestamp", datetime.utcnow())
    ext.engine = kwargs.get("engine", "paddleocr")
    ext.is_duplicate = kwargs.get("is_duplicate", False)
    return ext


# ─────────────────────────────── process_ocr_frame ───────────────────────────

class TestProcessOcrFrame:
    def test_success_with_text_extraction(self) -> None:
        """Task successfully extracts and saves text."""
        from app.tasks import process_ocr_frame

        mock_session = _make_mock_session()
        mock_extraction = MagicMock(id="ext-123")

        with patch("app.tasks._get_services") as mock_get_services:
            mock_db = MagicMock()
            mock_ocr_svc = MagicMock()
            mock_filter_svc = MagicMock()
            mock_session_model = MagicMock()
            mock_extraction_model = MagicMock()

            mock_db.query.return_value.filter.return_value.first.return_value = mock_session
            mock_ocr_svc.process_frame.return_value = _make_mock_ocr_response([("STOP", 0.95)])
            mock_filter_svc.filter_results.return_value = [
                TextResult(content="STOP", confidence=0.95, bounding_box=None)
            ]
            mock_filter_svc.is_duplicate.return_value = False
            mock_extraction_model.return_value = mock_extraction

            mock_get_services.return_value = (
                mock_db, mock_ocr_svc, mock_filter_svc, mock_session_model, mock_extraction_model
            )

            result = process_ocr_frame("base64frame", "test-session-id")

            assert result["status"] == "success"
            assert result["session_id"] == "test-session-id"
            assert result["texts_found"] == 1
            assert result["texts_saved"] == 1
            assert "ext-123" in result["extraction_ids"]
            mock_db.commit.assert_called_once()

    def test_raises_when_session_not_found(self) -> None:
        """Task raises ValueError when session does not exist."""
        from app.tasks import process_ocr_frame

        with patch("app.tasks._get_services") as mock_get_services:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None

            mock_get_services.return_value = (
                mock_db, MagicMock(), MagicMock(), MagicMock(), MagicMock()
            )

            with pytest.raises(ValueError, match="Session .* not found"):
                process_ocr_frame("base64frame", "nonexistent-session")

            mock_db.rollback.assert_called_once()

    def test_rolls_back_on_exception(self) -> None:
        """Task rolls back database on unexpected exception."""
        from app.tasks import process_ocr_frame

        with patch("app.tasks._get_services") as mock_get_services:
            mock_db = MagicMock()
            mock_ocr_svc = MagicMock()
            mock_ocr_svc.process_frame.side_effect = RuntimeError("OCR failed")

            mock_get_services.return_value = (
                mock_db, mock_ocr_svc, MagicMock(), MagicMock(), MagicMock()
            )

            with pytest.raises(RuntimeError, match="OCR failed"):
                process_ocr_frame("base64frame", "test-session-id")

            mock_db.rollback.assert_called_once()
            mock_db.close.assert_called_once()

    def test_marks_duplicates_correctly(self) -> None:
        """Task marks duplicate extractions appropriately."""
        from app.tasks import process_ocr_frame

        mock_session = _make_mock_session()

        with patch("app.tasks._get_services") as mock_get_services:
            mock_db = MagicMock()
            mock_ocr_svc = MagicMock()
            mock_filter_svc = MagicMock()
            mock_session_model = MagicMock()
            mock_extraction_model = MagicMock()

            mock_db.query.return_value.filter.return_value.first.return_value = mock_session
            mock_ocr_svc.process_frame.return_value = _make_mock_ocr_response([
                ("STOP", 0.95),
                ("STOP", 0.90),
            ])
            mock_filter_svc.filter_results.return_value = [
                TextResult(content="STOP", confidence=0.95, bounding_box=None),
                TextResult(content="STOP", confidence=0.90, bounding_box=None),
            ]
            mock_filter_svc.is_duplicate.side_effect = [False, True]
            mock_extraction_model.return_value = MagicMock(id="ext-1")

            mock_get_services.return_value = (
                mock_db, mock_ocr_svc, mock_filter_svc, mock_session_model, mock_extraction_model
            )

            result = process_ocr_frame("base64frame", "test-session-id")

            assert mock_filter_svc.is_duplicate.call_count == 2
            mock_db.commit.assert_called_once()

    def test_includes_location_data(self) -> None:
        """Task includes latitude/longitude in extraction when provided."""
        from app.tasks import process_ocr_frame

        mock_session = _make_mock_session()

        with patch("app.tasks._get_services") as mock_get_services:
            mock_db = MagicMock()
            mock_ocr_svc = MagicMock()
            mock_filter_svc = MagicMock()
            mock_session_model = MagicMock()
            mock_extraction_model = MagicMock()

            mock_db.query.return_value.filter.return_value.first.return_value = mock_session
            mock_ocr_svc.process_frame.return_value = _make_mock_ocr_response([("EXIT", 0.92)])
            mock_filter_svc.filter_results.return_value = [
                TextResult(content="EXIT", confidence=0.92, bounding_box=None)
            ]
            mock_filter_svc.is_duplicate.return_value = False
            mock_extraction_model.return_value = MagicMock(id="ext-1")

            mock_get_services.return_value = (
                mock_db, mock_ocr_svc, mock_filter_svc, mock_session_model, mock_extraction_model
            )

            process_ocr_frame(
                "base64frame",
                "test-session-id",
                latitude=35.6762,
                longitude=139.6503,
            )

            call_kwargs = mock_extraction_model.call_args[1]
            assert call_kwargs["latitude"] == 35.6762
            assert call_kwargs["longitude"] == 139.6503


# ─────────────────────────────── save_extractions_batch ──────────────────────

class TestSaveExtractionsBatch:
    def test_saves_multiple_extractions(self) -> None:
        """Task bulk saves a list of extractions."""
        from app.tasks import save_extractions_batch

        extractions = [
            {
                "session_id": "session-1",
                "content": "STOP",
                "confidence": 0.95,
                "bounding_box": None,
                "latitude": 35.0,
                "longitude": 139.0,
                "altitude": None,
                "engine": "paddleocr",
                "is_duplicate": False,
            },
            {
                "session_id": "session-1",
                "content": "YIELD",
                "confidence": 0.88,
                "bounding_box": [[0, 0], [100, 0], [100, 20], [0, 20]],
                "latitude": None,
                "longitude": None,
                "altitude": None,
                "engine": "paddleocr",
                "is_duplicate": False,
            },
        ]

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            result = save_extractions_batch(extractions)

            assert result["status"] == "success"
            assert result["saved"] == 2
            mock_db.bulk_save_objects.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.close.assert_called_once()

    def test_handles_empty_list(self) -> None:
        """Task handles empty extraction list gracefully."""
        from app.tasks import save_extractions_batch

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            result = save_extractions_batch([])

            assert result["status"] == "success"
            assert result["saved"] == 0
            mock_db.commit.assert_called_once()

    def test_rolls_back_on_failure(self) -> None:
        """Task rolls back on database error."""
        from app.tasks import save_extractions_batch

        extractions = [{"session_id": "s1", "content": "STOP", "confidence": 0.9}]

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_db.bulk_save_objects.side_effect = Exception("DB error")
            mock_session_local.return_value = mock_db

            with pytest.raises(Exception, match="DB error"):
                save_extractions_batch(extractions)

            mock_db.rollback.assert_called_once()
            mock_db.close.assert_called_once()

    def test_uses_default_engine(self) -> None:
        """Task uses paddleocr as default engine when not specified."""
        from app.tasks import save_extractions_batch

        extractions = [
            {
                "session_id": "session-1",
                "content": "STOP",
                "confidence": 0.95,
            }
        ]

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            save_extractions_batch(extractions)

            saved_obj = mock_db.bulk_save_objects.call_args[0][0][0]
            assert saved_obj.engine == "paddleocr"
            assert saved_obj.is_duplicate is False


# ─────────────────────────────── cleanup_old_sessions ────────────────────────

class TestCleanupOldSessions:
    def test_archives_old_active_sessions(self) -> None:
        """Task archives sessions older than 30 days."""
        from app.tasks import cleanup_old_sessions

        old_session = MagicMock()
        old_session.status = "active"
        old_session.started_at = datetime.utcnow() - timedelta(days=31)
        old_session.ended_at = None

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.all.return_value = [old_session]
            mock_session_local.return_value = mock_db

            result = cleanup_old_sessions()

            assert result["status"] == "success"
            assert result["archived"] == 1
            assert old_session.status == "archived"
            assert old_session.ended_at is not None
            mock_db.commit.assert_called_once()

    def test_no_sessions_to_archive(self) -> None:
        """Task returns zero when no old sessions exist."""
        from app.tasks import cleanup_old_sessions

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.all.return_value = []
            mock_session_local.return_value = mock_db

            result = cleanup_old_sessions()

            assert result["status"] == "success"
            assert result["archived"] == 0
            mock_db.commit.assert_called_once()

    def test_rolls_back_on_failure(self) -> None:
        """Task rolls back on error."""
        from app.tasks import cleanup_old_sessions

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_db.query.side_effect = Exception("Query failed")
            mock_session_local.return_value = mock_db

            with pytest.raises(Exception, match="Query failed"):
                cleanup_old_sessions()

            mock_db.rollback.assert_called_once()
            mock_db.close.assert_called_once()


# ─────────────────────────────── export_session_data ─────────────────────────

class TestExportSessionData:
    def test_exports_session_with_extractions(self) -> None:
        """Task exports session data including extractions."""
        from app.tasks import export_session_data

        mock_session = _make_mock_session()
        mock_session.started_at = datetime(2024, 1, 1, 12, 0, 0)
        mock_session.ended_at = None

        mock_extraction = _make_mock_extraction(
            extraction_id="ext-1",
            content="STOP",
            confidence=0.95,
            bounding_box=json.dumps([[0, 0], [100, 0], [100, 20], [0, 20]]),
            latitude=35.0,
            longitude=139.0,
            timestamp=datetime(2024, 1, 1, 12, 5, 0),
        )

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_query = MagicMock()
            mock_db.query.side_effect = lambda model: mock_query
            mock_query.filter.return_value.first.side_effect = [mock_session, mock_session]
            mock_query.filter.return_value.order_by.return_value.all.return_value = [mock_extraction]
            mock_session_local.return_value = mock_db

            result = export_session_data("test-session-id")

            assert result["session"]["id"] == "test-session-id"
            assert result["session"]["title"] == "Test Session"
            assert result["total"] == 1
            assert result["extractions"][0]["content"] == "STOP"
            assert result["extractions"][0]["confidence"] == 0.95

    def test_raises_when_session_not_found(self) -> None:
        """Task raises ValueError when session does not exist."""
        from app.tasks import export_session_data

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_session_local.return_value = mock_db

            with pytest.raises(ValueError, match="Session .* not found"):
                export_session_data("nonexistent-session")

            mock_db.close.assert_called_once()

    def test_handles_null_ended_at(self) -> None:
        """Task handles sessions with null ended_at correctly."""
        from app.tasks import export_session_data

        mock_session = _make_mock_session()
        mock_session.started_at = datetime(2024, 1, 1, 12, 0, 0)
        mock_session.ended_at = None

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_query = MagicMock()
            mock_db.query.side_effect = lambda model: mock_query
            mock_query.filter.return_value.first.return_value = mock_session
            mock_query.filter.return_value.order_by.return_value.all.return_value = []
            mock_session_local.return_value = mock_db

            result = export_session_data("test-session-id")

            assert result["session"]["ended_at"] is None

    def test_parses_bounding_box_json(self) -> None:
        """Task parses bounding_box JSON string into list."""
        from app.tasks import export_session_data

        mock_session = _make_mock_session()
        mock_session.started_at = datetime(2024, 1, 1, 12, 0, 0)
        mock_session.ended_at = None

        bbox = [[0, 0], [100, 0], [100, 20], [0, 20]]
        mock_extraction = _make_mock_extraction(
            bounding_box=json.dumps(bbox),
        )

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_query = MagicMock()
            mock_db.query.side_effect = lambda model: mock_query
            mock_query.filter.return_value.first.return_value = mock_session
            mock_query.filter.return_value.order_by.return_value.all.return_value = [mock_extraction]
            mock_session_local.return_value = mock_db

            result = export_session_data("test-session-id")

            assert result["extractions"][0]["bounding_box"] == bbox

    def test_handles_null_bounding_box(self) -> None:
        """Task handles extractions with null bounding_box."""
        from app.tasks import export_session_data

        mock_session = _make_mock_session()
        mock_session.started_at = datetime(2024, 1, 1, 12, 0, 0)
        mock_session.ended_at = None

        mock_extraction = _make_mock_extraction(bounding_box=None)

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_query = MagicMock()
            mock_db.query.side_effect = lambda model: mock_query
            mock_query.filter.return_value.first.return_value = mock_session
            mock_query.filter.return_value.order_by.return_value.all.return_value = [mock_extraction]
            mock_session_local.return_value = mock_db

            result = export_session_data("test-session-id")

            assert result["extractions"][0]["bounding_box"] is None

    def test_closes_db_session(self) -> None:
        """Task always closes database session."""
        from app.tasks import export_session_data

        with patch("app.database.SessionLocal") as mock_session_local:
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_session_local.return_value = mock_db

            with pytest.raises(ValueError):
                export_session_data("test-session-id")

            mock_db.close.assert_called_once()
