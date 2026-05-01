"""
SignReader API — Phase 2 (Optimized)
All Phase 1 endpoints plus async OCR via Celery, Redis caching,
keyword filtering, export, and session statistics.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from celery.result import AsyncResult
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, create_tables
from app.models import Extraction, Session as SessionModel
from app.schemas import (
    CacheStats,
    ExtractionCreate,
    ExtractionResponse,
    FilterConfig,
    OCRRequest,
    OCRResponse,
    SessionCreate,
    SessionResponse,
    SessionStats,
    TaskResponse,
    TaskStatusResponse,
)
from app.services.cache_service import CacheService
from app.services.filter_service import FilterService
from app.services.ocr_service import OCRService
from app.tasks import celery_app, process_ocr_frame

logger = logging.getLogger(__name__)

# Singletons
_ocr_service: OCRService | None = None
_cache_service: CacheService | None = None
_filter_service: FilterService | None = None


def get_ocr_service() -> OCRService:
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service


def get_cache_service() -> CacheService:
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service


def get_filter_service() -> FilterService:
    global _filter_service
    if _filter_service is None:
        cache = get_cache_service()
        _filter_service = FilterService(cache_service=cache)
    return _filter_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    logger.info("SignReader Optimized API started.")
    yield


app = FastAPI(
    title="SignReader API (Optimized)",
    version="0.2.0",
    description="Smartphone video OCR sign-reading backend — Phase 2 with async processing",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────── Health ──────────────────────────────────────

@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "version": "0.2.0",
        "ocr_engine": "paddleocr",
        "async_processing": True,
    }


# ─────────────────────────────── Sessions ────────────────────────────────────

@app.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(body: SessionCreate, db: Session = Depends(get_db)) -> SessionModel:
    db_session = SessionModel(
        title=body.title,
        description=body.description,
        user_id=body.user_id,
        status="active",
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


@app.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, db: Session = Depends(get_db)) -> SessionModel:
    db_session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if db_session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return db_session


@app.get("/sessions/{session_id}/stats", response_model=SessionStats)
def session_stats(session_id: str, db: Session = Depends(get_db)) -> SessionStats:
    db_session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if db_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = (
        db.query(Extraction)
        .filter(Extraction.session_id == session_id)
        .all()
    )
    total = len(rows)
    duplicates = sum(1 for r in rows if r.is_duplicate)
    unique_texts = len({r.content for r in rows if not r.is_duplicate})
    avg_confidence = (sum(r.confidence for r in rows) / total) if total else 0.0

    return SessionStats(
        session_id=session_id,
        total_extractions=total,
        unique_texts=unique_texts,
        duplicate_extractions=duplicates,
        avg_confidence=round(avg_confidence, 4),
    )


# ─────────────────────────────── OCR (sync) ──────────────────────────────────

@app.post("/ocr/process", response_model=OCRResponse)
def process_ocr_sync(
    body: OCRRequest,
    db: Session = Depends(get_db),
    ocr_svc: OCRService = Depends(get_ocr_service),
    filter_svc: FilterService = Depends(get_filter_service),
) -> OCRResponse:
    db_session = db.query(SessionModel).filter(SessionModel.id == body.session_id).first()
    if db_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        response = ocr_svc.process_frame(body.frame)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Apply dedup + keyword filter
    response.texts = filter_svc.filter_results(response.texts, body.session_id)
    return response


# ─────────────────────────────── OCR (async) ─────────────────────────────────

@app.post(
    "/ocr/process/async",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def process_ocr_async(
    body: OCRRequest,
    db: Session = Depends(get_db),
) -> TaskResponse:
    db_session = db.query(SessionModel).filter(SessionModel.id == body.session_id).first()
    if db_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    task = process_ocr_frame.delay(
        body.frame,
        body.session_id,
        body.latitude,
        body.longitude,
    )
    return TaskResponse(
        task_id=task.id,
        status="queued",
        message="OCR task queued for processing",
    )


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    result = AsyncResult(task_id, app=celery_app)
    if result.state == "PENDING":
        return TaskStatusResponse(task_id=task_id, status="pending")
    if result.state == "SUCCESS":
        return TaskStatusResponse(task_id=task_id, status="success", result=result.result)
    if result.state == "FAILURE":
        return TaskStatusResponse(
            task_id=task_id, status="failure", error=str(result.info)
        )
    return TaskStatusResponse(task_id=task_id, status=result.state.lower())


# ─────────────────────────────── Extractions ─────────────────────────────────

@app.post(
    "/extract/save",
    response_model=ExtractionResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_extraction(
    body: ExtractionCreate,
    db: Session = Depends(get_db),
    filter_svc: FilterService = Depends(get_filter_service),
) -> Extraction:
    db_session = db.query(SessionModel).filter(SessionModel.id == body.session_id).first()
    if db_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    is_dup = filter_svc.is_duplicate(body.content, body.session_id)
    if not is_dup:
        filter_svc.add_to_seen(body.session_id, body.content)

    extraction = Extraction(
        session_id=body.session_id,
        content=body.content,
        confidence=body.confidence,
        bounding_box=json.dumps(body.bounding_box) if body.bounding_box is not None else None,
        latitude=body.latitude,
        longitude=body.longitude,
        altitude=body.altitude,
        engine=body.engine,
        is_duplicate=is_dup,
    )
    db.add(extraction)
    db.commit()
    db.refresh(extraction)

    if extraction.bounding_box and isinstance(extraction.bounding_box, str):
        extraction.bounding_box = json.loads(extraction.bounding_box)

    return extraction


@app.get("/extract/{session_id}", response_model=List[ExtractionResponse])
def list_extractions(session_id: str, db: Session = Depends(get_db)) -> List[Extraction]:
    extractions = (
        db.query(Extraction)
        .filter(Extraction.session_id == session_id)
        .order_by(Extraction.created_at.asc())
        .all()
    )
    for ext in extractions:
        if ext.bounding_box and isinstance(ext.bounding_box, str):
            ext.bounding_box = json.loads(ext.bounding_box)
    return extractions


# ─────────────────────────────── Cache ───────────────────────────────────────

@app.get("/cache/stats", response_model=CacheStats)
def cache_stats(
    cache_svc: CacheService = Depends(get_cache_service),
) -> CacheStats:
    return cache_svc.get_stats()


@app.delete("/cache/{session_id}")
def clear_cache(
    session_id: str,
    cache_svc: CacheService = Depends(get_cache_service),
) -> dict:
    cache_svc.clear_all_session_data(session_id)
    return {"status": "ok", "message": f"Cache cleared for session {session_id}"}


# ─────────────────────────────── Filters ─────────────────────────────────────

@app.post("/filters/keywords", status_code=status.HTTP_200_OK)
def set_filter_keywords(
    body: FilterConfig,
    filter_svc: FilterService = Depends(get_filter_service),
) -> dict:
    filter_svc.set_keywords(body.session_id, body.keywords, body.mode)
    return {"status": "ok", "session_id": body.session_id, "keywords": body.keywords}


@app.get("/filters/keywords/{session_id}", response_model=FilterConfig)
def get_filter_keywords(
    session_id: str,
    filter_svc: FilterService = Depends(get_filter_service),
) -> FilterConfig:
    return filter_svc.get_keywords(session_id)


# ─────────────────────────────── Export ──────────────────────────────────────

@app.get("/export/{session_id}")
def export_session(session_id: str, db: Session = Depends(get_db)) -> JSONResponse:
    db_session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if db_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    extractions = (
        db.query(Extraction)
        .filter(Extraction.session_id == session_id)
        .order_by(Extraction.created_at.asc())
        .all()
    )

    payload: Dict[str, Any] = {
        "session": {
            "id": db_session.id,
            "title": db_session.title,
            "description": db_session.description,
            "status": db_session.status,
            "started_at": db_session.started_at.isoformat(),
            "ended_at": db_session.ended_at.isoformat() if db_session.ended_at else None,
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
        "total_extractions": len(extractions),
    }

    return JSONResponse(content=payload)
