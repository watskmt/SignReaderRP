"""
SignReader Celery tasks.
Workers run OCR asynchronously, batch-save extractions, and perform maintenance.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from celery import Celery
from celery.schedules import crontab

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "signreader",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "cleanup-old-sessions": {
            "task": "app.tasks.cleanup_old_sessions",
            "schedule": crontab(hour=2, minute=0),  # daily at 02:00 UTC
        }
    },
)


def _get_services():
    """Lazy imports to avoid circular imports and load models only in worker process."""
    from app.database import SessionLocal
    from app.models import Extraction, Session as SessionModel
    from app.services.cache_service import CacheService
    from app.services.filter_service import FilterService
    from app.services.ocr_service import OCRService

    cache = CacheService()
    filter_svc = FilterService(cache_service=cache)
    ocr_svc = OCRService()
    db = SessionLocal()
    return db, ocr_svc, filter_svc, SessionModel, Extraction


@celery_app.task(
    name="app.tasks.process_ocr_frame",
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=2,
)
def process_ocr_frame(
    self,
    frame_b64: str,
    session_id: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Process a single video frame through OCR, deduplicate, and save results.

    Returns a dict with extracted texts and their metadata.
    """
    db, ocr_svc, filter_svc, SessionModel, Extraction = _get_services()

    try:
        # Validate session exists
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        # Run OCR
        ocr_response = ocr_svc.process_frame(frame_b64)

        # Filter duplicates and apply keyword rules
        filtered_texts = filter_svc.filter_results(ocr_response.texts, session_id)

        saved_ids: List[str] = []
        for text_result in filtered_texts:
            is_dup = filter_svc.is_duplicate(text_result.content, session_id)
            if not is_dup:
                filter_svc.add_to_seen(session_id, text_result.content)

            extraction = Extraction(
                session_id=session_id,
                content=text_result.content,
                confidence=text_result.confidence,
                bounding_box=(
                    json.dumps(text_result.bounding_box)
                    if text_result.bounding_box is not None
                    else None
                ),
                latitude=latitude,
                longitude=longitude,
                engine="paddleocr",
                is_duplicate=is_dup,
            )
            db.add(extraction)
            db.flush()
            saved_ids.append(extraction.id)

        db.commit()

        return {
            "status": "success",
            "session_id": session_id,
            "texts_found": len(ocr_response.texts),
            "texts_saved": len(saved_ids),
            "extraction_ids": saved_ids,
            "processing_time_ms": ocr_response.processing_time_ms,
        }

    except Exception as exc:
        db.rollback()
        logger.error("process_ocr_frame failed: %s", exc, exc_info=True)
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.save_extractions_batch")
def save_extractions_batch(extractions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Bulk-insert a list of extraction dicts into the database.

    Each dict should match the Extraction model fields.
    """
    from app.database import SessionLocal
    from app.models import Extraction

    db = SessionLocal()
    try:
        rows = [
            Extraction(
                session_id=ext["session_id"],
                content=ext["content"],
                confidence=ext["confidence"],
                bounding_box=(
                    json.dumps(ext["bounding_box"])
                    if ext.get("bounding_box") is not None
                    else None
                ),
                latitude=ext.get("latitude"),
                longitude=ext.get("longitude"),
                altitude=ext.get("altitude"),
                engine=ext.get("engine", "paddleocr"),
                is_duplicate=ext.get("is_duplicate", False),
            )
            for ext in extractions
        ]
        db.bulk_save_objects(rows)
        db.commit()
        return {"status": "success", "saved": len(rows)}
    except Exception as exc:
        db.rollback()
        logger.error("save_extractions_batch failed: %s", exc, exc_info=True)
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.cleanup_old_sessions")
def cleanup_old_sessions() -> Dict[str, Any]:
    """
    Archive sessions that have been active for more than 30 days.
    Runs daily via Celery Beat.
    """
    from app.database import SessionLocal
    from app.models import Session as SessionModel

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        old_sessions = (
            db.query(SessionModel)
            .filter(
                SessionModel.status == "active",
                SessionModel.started_at < cutoff,
            )
            .all()
        )

        count = len(old_sessions)
        for session in old_sessions:
            session.status = "archived"
            session.ended_at = datetime.utcnow()

        db.commit()
        logger.info("Archived %d old sessions.", count)
        return {"status": "success", "archived": count}
    except Exception as exc:
        db.rollback()
        logger.error("cleanup_old_sessions failed: %s", exc, exc_info=True)
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.export_session_data")
def export_session_data(session_id: str) -> Dict[str, Any]:
    """
    Generate a full JSON export of a session's extractions.
    Result is stored in the Celery result backend.
    """
    from app.database import SessionLocal
    from app.models import Extraction, Session as SessionModel

    db = SessionLocal()
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        extractions = (
            db.query(Extraction)
            .filter(Extraction.session_id == session_id)
            .order_by(Extraction.timestamp.asc())
            .all()
        )

        return {
            "session": {
                "id": session.id,
                "title": session.title,
                "description": session.description,
                "status": session.status,
                "started_at": session.started_at.isoformat(),
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            },
            "extractions": [
                {
                    "id": ext.id,
                    "content": ext.content,
                    "confidence": ext.confidence,
                    "bounding_box": json.loads(ext.bounding_box) if ext.bounding_box else None,
                    "latitude": ext.latitude,
                    "longitude": ext.longitude,
                    "altitude": ext.altitude,
                    "timestamp": ext.timestamp.isoformat(),
                    "engine": ext.engine,
                    "is_duplicate": ext.is_duplicate,
                }
                for ext in extractions
            ],
            "total": len(extractions),
        }
    finally:
        db.close()
