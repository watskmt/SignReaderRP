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
from fastapi.responses import HTMLResponse, JSONResponse
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
    _migrate_add_image_url()
    logger.info("SignReader Optimized API started.")
    yield


def _migrate_add_image_url() -> None:
    """既存DBにimage_urlカラムがなければ追加する（冪等）。"""
    from sqlalchemy import text
    from app.database import engine
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE extractions ADD COLUMN IF NOT EXISTS image_url VARCHAR(500)"
            ))
            conn.commit()
        except Exception:
            pass


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

@app.get("/sessions", response_model=List[SessionResponse])
def list_sessions(db: Session = Depends(get_db)) -> List[SessionModel]:
    return (
        db.query(SessionModel)
        .order_by(SessionModel.created_at.desc())
        .all()
    )


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


# ─────────────────────────────── Admin UI ────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_ui() -> str:
    return """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SignReader 管理画面</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  body { background: #f8f9fa; }
  .extraction-row.duplicate { opacity: 0.5; }
  .confidence-bar { height: 6px; border-radius: 3px; background: #dee2e6; }
  .confidence-fill { height: 100%; border-radius: 3px; background: #198754; }
  .session-card { cursor: pointer; transition: box-shadow .15s; }
  .session-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.1); }
  pre { white-space: pre-wrap; word-break: break-all; }
</style>
</head>
<body>
<div class="container py-4">
  <div class="d-flex align-items-center mb-4">
    <h1 class="h3 mb-0 me-3">SignReader 管理画面</h1>
    <span id="session-count" class="badge bg-secondary">読込中...</span>
    <button class="btn btn-sm btn-outline-secondary ms-auto" onclick="loadSessions()">更新</button>
  </div>

  <div id="sessions-list" class="row g-3"></div>

  <!-- Extractions Modal -->
  <div class="modal fade" id="extractionModal" tabindex="-1">
    <div class="modal-dialog modal-xl modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title" id="modal-title">抽出結果</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
        </div>
        <div class="modal-body">
          <div id="modal-stats" class="row g-2 mb-3"></div>
          <div class="form-check form-switch mb-2">
            <input class="form-check-input" type="checkbox" id="hide-duplicates">
            <label class="form-check-label" for="hide-duplicates">重複を非表示</label>
          </div>
          <table class="table table-sm table-hover">
            <thead class="table-light">
              <tr>
                <th>テキスト</th>
                <th style="width:90px">信頼度</th>
                <th style="width:60px">重複</th>
                <th style="width:160px">GPS</th>
                <th style="width:160px">日時</th>
              </tr>
            </thead>
            <tbody id="extraction-tbody"></tbody>
          </table>
        </div>
        <div class="modal-footer">
          <a id="export-link" href="#" class="btn btn-outline-primary btn-sm" target="_blank">JSONエクスポート</a>
          <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">閉じる</button>
        </div>
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
const BASE = '';
let allExtractions = [];

async function loadSessions() {
  const res = await fetch(BASE + '/sessions');
  const sessions = await res.json();
  document.getElementById('session-count').textContent = sessions.length + ' セッション';

  const statsMap = {};
  await Promise.all(sessions.map(async s => {
    try {
      const r = await fetch(BASE + '/sessions/' + s.id + '/stats');
      statsMap[s.id] = await r.json();
    } catch {}
  }));

  const list = document.getElementById('sessions-list');
  list.innerHTML = sessions.map(s => {
    const stats = statsMap[s.id] || {};
    const date = new Date(s.created_at).toLocaleString('ja-JP');
    const statusColor = s.status === 'active' ? 'success' : 'secondary';
    return `
      <div class="col-md-6 col-lg-4">
        <div class="card session-card h-100" onclick="openSession('${s.id}', '${escHtml(s.title)}')">
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-start mb-2">
              <h6 class="card-title mb-0">${escHtml(s.title)}</h6>
              <span class="badge bg-${statusColor}">${s.status}</span>
            </div>
            <p class="text-muted small mb-2">${date}</p>
            <div class="row text-center g-1">
              <div class="col"><div class="fw-bold">${stats.total_extractions ?? '-'}</div><div class="text-muted" style="font-size:.75rem">抽出</div></div>
              <div class="col"><div class="fw-bold">${stats.unique_texts ?? '-'}</div><div class="text-muted" style="font-size:.75rem">ユニーク</div></div>
              <div class="col"><div class="fw-bold">${stats.duplicate_extractions ?? '-'}</div><div class="text-muted" style="font-size:.75rem">重複</div></div>
            </div>
          </div>
        </div>
      </div>`;
  }).join('');
}

async function openSession(id, title) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('export-link').href = BASE + '/export/' + id;
  document.getElementById('extraction-tbody').innerHTML = '<tr><td colspan="5" class="text-center text-muted">読込中...</td></tr>';

  const modal = new bootstrap.Modal(document.getElementById('extractionModal'));
  modal.show();

  const [extRes, statsRes] = await Promise.all([
    fetch(BASE + '/extract/' + id),
    fetch(BASE + '/sessions/' + id + '/stats'),
  ]);
  allExtractions = await extRes.json();
  const stats = await statsRes.json();

  document.getElementById('modal-stats').innerHTML = `
    <div class="col-auto"><span class="badge bg-primary">${stats.total_extractions} 件</span></div>
    <div class="col-auto"><span class="badge bg-success">${stats.unique_texts} ユニーク</span></div>
    <div class="col-auto"><span class="badge bg-secondary">${stats.duplicate_extractions} 重複</span></div>
    <div class="col-auto"><span class="badge bg-info text-dark">平均信頼度 ${(stats.avg_confidence * 100).toFixed(1)}%</span></div>`;

  renderExtractions();
}

function renderExtractions() {
  const hideDup = document.getElementById('hide-duplicates').checked;
  const rows = allExtractions
    .filter(e => !hideDup || !e.is_duplicate)
    .map(e => {
      const pct = Math.round(e.confidence * 100);
      const gps = e.latitude ? `${e.latitude.toFixed(5)}, ${e.longitude.toFixed(5)}` : '-';
      const date = new Date(e.timestamp).toLocaleString('ja-JP');
      return `<tr class="extraction-row ${e.is_duplicate ? 'duplicate' : ''}">
        <td>${escHtml(e.content)}</td>
        <td>
          <div class="d-flex align-items-center gap-1">
            <small>${pct}%</small>
            <div class="confidence-bar flex-grow-1"><div class="confidence-fill" style="width:${pct}%"></div></div>
          </div>
        </td>
        <td>${e.is_duplicate ? '<span class="badge bg-secondary">重複</span>' : ''}</td>
        <td><small class="text-muted">${gps}</small></td>
        <td><small class="text-muted">${date}</small></td>
      </tr>`;
    }).join('');
  document.getElementById('extraction-tbody').innerHTML = rows || '<tr><td colspan="5" class="text-center text-muted">データなし</td></tr>';
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

document.getElementById('hide-duplicates').addEventListener('change', renderExtractions);

loadSessions();
</script>
</body>
</html>"""
