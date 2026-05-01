"""
Unit tests for OCRService.
PaddleOCR is mocked to avoid requiring the model in CI.
"""
from __future__ import annotations

import base64
import io
from typing import Any, List
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from app.services.ocr_service import MAX_IMAGE_WIDTH, OCRService


# ─────────────────────────────── Helpers ─────────────────────────────────────

def _make_png_b64(width: int = 100, height: int = 100) -> str:
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _mock_paddle_result(texts: List[tuple]) -> List[Any]:
    """Build a PaddleOCR-shaped result list from [(text, confidence), ...]."""
    lines = [
        [[[0, 0], [100, 0], [100, 20], [0, 20]], (text, conf)]
        for text, conf in texts
    ]
    return [lines]


# ─────────────────────────────── Tests ───────────────────────────────────────

def test_ocr_service_initializes() -> None:
    svc = OCRService()
    assert svc is not None
    assert svc._ocr is None  # Lazy — not yet loaded


def test_decode_frame_valid_base64() -> None:
    svc = OCRService()
    b64 = _make_png_b64(50, 50)
    arr = svc.decode_frame(b64)
    assert isinstance(arr, np.ndarray)
    assert arr.shape == (50, 50, 3)


def test_decode_frame_invalid_base64() -> None:
    svc = OCRService()
    with pytest.raises(ValueError, match="(?i)invalid|base64|decode"):
        svc.decode_frame("!!!not_valid_base64!!!")


def test_preprocess_image_resizes_large() -> None:
    svc = OCRService()
    large = np.zeros((720, 1920, 3), dtype=np.uint8)
    result = svc.preprocess_image(large)
    assert result.shape[1] == MAX_IMAGE_WIDTH
    assert result.shape[1] <= MAX_IMAGE_WIDTH


def test_preprocess_image_leaves_small() -> None:
    svc = OCRService()
    small = np.zeros((100, 200, 3), dtype=np.uint8)
    result = svc.preprocess_image(small)
    assert result.shape[1] == 200  # Width unchanged


def test_extract_text_filters_low_confidence() -> None:
    svc = OCRService()
    paddle_result = _mock_paddle_result([
        ("STOP", 0.95),
        ("blurry", 0.30),   # Below default threshold 0.6
        ("YIELD", 0.72),
    ])

    with patch.object(svc, "_get_ocr") as mock_get:
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = paddle_result
        mock_get.return_value = mock_ocr

        results = svc.extract_text(np.zeros((100, 100, 3), dtype=np.uint8))

    texts = [r.content for r in results]
    assert "STOP" in texts
    assert "YIELD" in texts
    assert "blurry" not in texts


def test_parse_paddle_result() -> None:
    svc = OCRService()
    raw = _mock_paddle_result([("SPEED LIMIT 50", 0.88), ("TOKYO", 0.91)])
    results = svc._parse_paddle_result(raw)
    assert len(results) == 2
    assert results[0].content == "SPEED LIMIT 50"
    assert abs(results[0].confidence - 0.88) < 1e-6
    assert results[1].content == "TOKYO"


def test_process_frame_returns_ocr_response(sample_image_b64: str) -> None:
    svc = OCRService()
    paddle_result = _mock_paddle_result([("EXIT", 0.95)])

    with patch.object(svc, "_get_ocr") as mock_get:
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = paddle_result
        mock_get.return_value = mock_ocr

        response = svc.process_frame(sample_image_b64)

    assert response.status == "success"
    assert response.engine == "paddleocr"
    assert response.processing_time_ms >= 0
    assert len(response.texts) == 1
    assert response.texts[0].content == "EXIT"


def test_process_frame_empty_image(sample_image_b64: str) -> None:
    svc = OCRService()

    with patch.object(svc, "_get_ocr") as mock_get:
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = [[]]  # No detections
        mock_get.return_value = mock_ocr

        response = svc.process_frame(sample_image_b64)

    assert response.status == "success"
    assert response.texts == []
