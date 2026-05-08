from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────── User ────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=255)


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────── Session ─────────────────────────────────────

class SessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    user_id: Optional[str] = None


class SessionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[Literal["active", "completed", "archived"]] = None
    ended_at: Optional[datetime] = None


class SessionResponse(BaseModel):
    id: str
    user_id: Optional[str]
    title: str
    description: Optional[str]
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────── Extraction ──────────────────────────────────

class ExtractionCreate(BaseModel):
    session_id: str
    content: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    bounding_box: Optional[Any] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    engine: str = Field(default="paddleocr", max_length=50)


class ExtractionResponse(BaseModel):
    id: str
    session_id: str
    content: str
    confidence: float
    bounding_box: Optional[Any]
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[float]
    timestamp: datetime
    engine: str
    is_duplicate: bool
    image_url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────── OCR ─────────────────────────────────────────

class TextResult(BaseModel):
    content: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    bounding_box: Optional[Any] = None


class OCRRequest(BaseModel):
    frame: str = Field(..., description="Base64-encoded image (PNG or JPEG)")
    session_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class OCRResponse(BaseModel):
    status: str
    texts: List[TextResult]
    processing_time_ms: float
    engine: str = "paddleocr"


# ─────────────────────────────── Tasks ───────────────────────────────────────

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None


# ─────────────────────────────── Cache ───────────────────────────────────────

class CacheStats(BaseModel):
    hit_rate: float
    total_keys: int
    memory_usage_mb: float


# ─────────────────────────────── Filter ──────────────────────────────────────

class FilterConfig(BaseModel):
    session_id: str
    keywords: List[str] = Field(default_factory=list)
    mode: Literal["include", "exclude"] = "include"


# ─────────────────────────────── Stats ───────────────────────────────────────

class SessionStats(BaseModel):
    session_id: str
    total_extractions: int
    unique_texts: int
    duplicate_extractions: int
    avg_confidence: float
