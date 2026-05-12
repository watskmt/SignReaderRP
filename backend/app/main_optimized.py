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
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
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
    # 画像保存ディレクトリを作成
    import os
    os.makedirs("/app/images", exist_ok=True)
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

import os as _os
_os.makedirs("/app/images", exist_ok=True)
app.mount("/images", StaticFiles(directory="/app/images"), name="images")


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


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)) -> Response:
    db_session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if db_session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(db_session)
    db.commit()
    return Response(status_code=204)


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


@app.get("/tasks/queue-stats")
def queue_stats() -> dict:
    """Return active/queued Celery task counts and per-session processing state."""
    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}

        active_sessions: dict = {}
        queued_sessions: dict = {}

        for tasks in active.values():
            for task in tasks:
                args = task.get("args", [])
                if len(args) >= 2:
                    sid = args[1]
                    active_sessions[sid] = active_sessions.get(sid, 0) + 1

        for tasks in reserved.values():
            for task in tasks:
                args = task.get("args", [])
                if len(args) >= 2:
                    sid = args[1]
                    queued_sessions[sid] = queued_sessions.get(sid, 0) + 1

        processing_sessions = {
            sid: {"active": active_sessions.get(sid, 0), "queued": queued_sessions.get(sid, 0)}
            for sid in set(list(active_sessions) + list(queued_sessions))
        }

        active_count = sum(len(v) for v in active.values())
        queued_count = sum(len(v) for v in reserved.values())
        return {
            "active": active_count,
            "queued": queued_count,
            "total": active_count + queued_count,
            "processing_sessions": processing_sessions,
        }
    except Exception:
        return {"active": 0, "queued": 0, "total": 0, "processing_sessions": {}, "error": "unreachable"}


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
  .card.selected { outline: 2px solid #0d6efd; }
  pre { white-space: pre-wrap; word-break: break-all; }
  #queue-indicator { display: inline-flex; align-items: center; gap: 6px; font-size: .85rem; }
  .queue-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  .queue-dot.idle { background: #198754; }
  .queue-dot.busy { background: #fd7e14; animation: pulse 1s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:.5; transform:scale(1.3); } }
</style>
</head>
<body>
<div class="container py-4">
  <div class="d-flex align-items-center mb-3">
    <h1 class="h3 mb-0 me-3">SignReader 管理画面</h1>
    <span id="session-count" class="badge bg-secondary me-2">読込中...</span>
    <div id="queue-indicator" class="me-auto">
      <div class="queue-dot idle" id="queue-dot"></div>
      <span id="queue-label" class="text-muted">待機中</span>
    </div>
    <button class="btn btn-sm btn-outline-secondary" onclick="loadSessions()">更新</button>
  </div>

  <!-- 一括操作バー -->
  <div class="d-flex align-items-center gap-2 mb-3">
    <div class="form-check mb-0">
      <input class="form-check-input" type="checkbox" id="select-all" onchange="toggleSelectAll()">
      <label class="form-check-label" for="select-all">すべて選択</label>
    </div>
    <span id="selected-count" class="text-muted small"></span>
    <button id="bulk-delete-btn" class="btn btn-danger btn-sm ms-auto d-none"
      onclick="bulkDelete()">選択したものを削除</button>
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
        <div class="card h-100" id="card-${s.id}">
          <div class="card-body session-card" onclick="openSession('${s.id}', '${escHtml(s.title)}')">
            <div class="d-flex justify-content-between align-items-start mb-2">
              <div class="d-flex align-items-center gap-2">
                <input class="form-check-input session-checkbox" type="checkbox"
                  value="${s.id}" onclick="event.stopPropagation(); updateSelection()">
                <h6 class="card-title mb-0">${escHtml(s.title)}</h6>
              </div>
              <div class="d-flex align-items-center gap-1">
                <span id="proc-${s.id}" class="d-none"></span>
                <span class="badge bg-${statusColor}">${s.status}</span>
              </div>
            </div>
            <p class="text-muted small mb-2">${date}</p>
            <div class="row text-center g-1">
              <div class="col"><div class="fw-bold">${stats.total_extractions ?? '-'}</div><div class="text-muted" style="font-size:.75rem">抽出</div></div>
              <div class="col"><div class="fw-bold">${stats.unique_texts ?? '-'}</div><div class="text-muted" style="font-size:.75rem">ユニーク</div></div>
              <div class="col"><div class="fw-bold">${stats.duplicate_extractions ?? '-'}</div><div class="text-muted" style="font-size:.75rem">重複</div></div>
            </div>
          </div>
          <div class="card-footer bg-transparent p-2">
            <button class="btn btn-outline-danger btn-sm w-100"
              onclick="confirmDelete('${s.id}', '${escHtml(s.title)}')">削除</button>
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

function getSelectedIds() {
  return [...document.querySelectorAll('.session-checkbox:checked')].map(c => c.value);
}

function updateSelection() {
  const ids = getSelectedIds();
  const total = document.querySelectorAll('.session-checkbox').length;
  document.getElementById('selected-count').textContent = ids.length ? `${ids.length} 件選択中` : '';
  document.getElementById('bulk-delete-btn').classList.toggle('d-none', ids.length === 0);
  document.getElementById('select-all').indeterminate = ids.length > 0 && ids.length < total;
  document.getElementById('select-all').checked = ids.length === total && total > 0;
  ids.forEach(id => document.getElementById('card-' + id)?.classList.add('selected'));
  document.querySelectorAll('.session-checkbox:not(:checked)').forEach(c => {
    document.getElementById('card-' + c.value)?.classList.remove('selected');
  });
}

function toggleSelectAll() {
  const checked = document.getElementById('select-all').checked;
  document.querySelectorAll('.session-checkbox').forEach(c => c.checked = checked);
  updateSelection();
}

async function bulkDelete() {
  const ids = getSelectedIds();
  if (!ids.length) return;
  if (!confirm(`${ids.length} 件のセッションを削除しますか？この操作は元に戻せません。`)) return;
  await Promise.all(ids.map(id => fetch(BASE + '/sessions/' + id, { method: 'DELETE' })));
  loadSessions();
}

async function confirmDelete(id, title) {
  if (!confirm(`「${title}」を削除しますか？この操作は元に戻せません。`)) return;
  const res = await fetch(BASE + '/sessions/' + id, { method: 'DELETE' });
  if (res.ok || res.status === 204) {
    loadSessions();
  } else {
    alert('削除に失敗しました');
  }
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

document.getElementById('hide-duplicates').addEventListener('change', renderExtractions);

async function updateQueueStats() {
  try {
    const res = await fetch(BASE + '/tasks/queue-stats');
    const data = await res.json();
    const dot = document.getElementById('queue-dot');
    const label = document.getElementById('queue-label');

    // グローバル表示
    if (data.total > 0) {
      dot.className = 'queue-dot busy';
      label.textContent = `変換中 ${data.total} 件`;
      label.style.color = '#fd7e14';
      label.style.fontWeight = '600';
    } else {
      dot.className = 'queue-dot idle';
      label.textContent = data.error ? '(ワーカー接続不可)' : '待機中';
      label.style.color = '';
      label.style.fontWeight = '';
    }

    // セッションごとのバッジ更新
    const processing = data.processing_sessions || {};
    document.querySelectorAll('[id^="proc-"]').forEach(el => {
      const sid = el.id.replace('proc-', '');
      const info = processing[sid];
      if (info) {
        const total = (info.active || 0) + (info.queued || 0);
        el.className = '';
        el.innerHTML = `<span class="badge bg-warning text-dark d-inline-flex align-items-center gap-1">
          <span class="spinner-border spinner-border-sm" style="width:.6rem;height:.6rem"></span>
          変換中 ${total}
        </span>`;
      } else {
        el.className = 'd-none';
        el.innerHTML = '';
      }
    });
  } catch {}
}

updateQueueStats();
setInterval(updateQueueStats, 2000);
loadSessions();
</script>
</body>
</html>"""
