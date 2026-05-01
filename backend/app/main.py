"""
SignReader API — Phase 1
Synchronous OCR endpoints with PostgreSQL persistence.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import get_db, create_tables
from app.models import Extraction, Session as SessionModel
from app.schemas import (
    ExtractionCreate,
    ExtractionResponse,
    OCRRequest,
    OCRResponse,
    SessionCreate,
    SessionResponse,
)
from app.services.ocr_service import OCRService

logger = logging.getLogger(__name__)

# Singleton OCR service (model loads once on first use)
_ocr_service: OCRService | None = None


def get_ocr_service() -> OCRService:
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    logger.info("SignReader API started — tables ensured.")
    yield


app = FastAPI(
    title="SignReader API",
    version="0.1.0",
    description="Smartphone video OCR sign-reading backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────── Health ──────────────────────────────────────

@app.get("/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "version": "0.1.0",
        "ocr_engine": "paddleocr",
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


# ─────────────────────────────── OCR ─────────────────────────────────────────

@app.post("/ocr/process", response_model=OCRResponse)
def process_ocr(
    body: OCRRequest,
    db: Session = Depends(get_db),
    ocr_svc: OCRService = Depends(get_ocr_service),
) -> OCRResponse:
    # Verify session exists
    db_session = db.query(SessionModel).filter(SessionModel.id == body.session_id).first()
    if db_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        response = ocr_svc.process_frame(body.frame)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return response


# ─────────────────────────────── Extractions ─────────────────────────────────

@app.post(
    "/extract/save",
    response_model=ExtractionResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_extraction(
    body: ExtractionCreate, db: Session = Depends(get_db)
) -> Extraction:
    # Verify session exists
    db_session = db.query(SessionModel).filter(SessionModel.id == body.session_id).first()
    if db_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    extraction = Extraction(
        session_id=body.session_id,
        content=body.content,
        confidence=body.confidence,
        bounding_box=json.dumps(body.bounding_box) if body.bounding_box is not None else None,
        latitude=body.latitude,
        longitude=body.longitude,
        altitude=body.altitude,
        engine=body.engine,
        is_duplicate=False,
    )
    db.add(extraction)
    db.commit()
    db.refresh(extraction)

    # Deserialise bounding_box back to Python object for response
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
