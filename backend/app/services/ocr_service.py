"""
OCRService — wraps PaddleOCR with image preprocessing and confidence filtering.
"""
from __future__ import annotations

import base64
import io
import logging
import time
from typing import Any, List, Optional

import numpy as np
from PIL import Image, ImageEnhance

from app.config import settings
from app.schemas import OCRResponse, TextResult

logger = logging.getLogger(__name__)

# Maximum width for input images. Larger images are scaled down.
MAX_IMAGE_WIDTH = 1280


class OCRService:
    """
    Wraps PaddleOCR with lazy model initialization, image preprocessing,
    and confidence-based result filtering.
    """

    def __init__(self) -> None:
        self._ocr: Any = None  # Lazy-initialised PaddleOCR instance

    def _get_ocr(self) -> Any:
        """Lazy-load PaddleOCR on first use to avoid import-time overhead."""
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR  # type: ignore

                logger.info("Initialising PaddleOCR model (this may take a moment)…")
                self._ocr = PaddleOCR(use_gpu=False, lang="japan", show_log=False)
                logger.info("PaddleOCR ready.")
            except ImportError:
                # Allow tests to run without PaddleOCR installed
                logger.warning(
                    "paddleocr not installed — OCRService will return empty results."
                )
                self._ocr = None
        return self._ocr

    # ──────────────────────────────── Decoding ────────────────────────────────

    def decode_frame(self, base64_str: str) -> np.ndarray:
        """
        Decode a base64-encoded image string into a numpy array (H, W, C) uint8.

        Raises ValueError on invalid base64 or non-image data.
        """
        # Strip optional data-URL prefix: "data:image/png;base64,..."
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]

        try:
            image_bytes = base64.b64decode(base64_str, validate=True)
        except Exception as exc:
            raise ValueError(f"Invalid base64 string: {exc}") from exc

        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            raise ValueError(f"Cannot decode image from base64 data: {exc}") from exc

        return np.array(image)

    # ──────────────────────────────── Preprocessing ───────────────────────────

    def preprocess_image(self, img: np.ndarray) -> np.ndarray:
        """
        Resize image if wider than MAX_IMAGE_WIDTH and apply grayscale enhancement
        to improve OCR accuracy on low-contrast signs.

        Returns a numpy array suitable for PaddleOCR inference.
        """
        pil_img = Image.fromarray(img)
        width, height = pil_img.size

        if width > MAX_IMAGE_WIDTH:
            scale = MAX_IMAGE_WIDTH / width
            new_height = int(height * scale)
            pil_img = pil_img.resize(
                (MAX_IMAGE_WIDTH, new_height), Image.Resampling.LANCZOS
            )

        # Enhance contrast slightly to help with faded or low-contrast signs
        enhancer = ImageEnhance.Contrast(pil_img)
        pil_img = enhancer.enhance(1.2)

        return np.array(pil_img)

    # ──────────────────────────────── Result parsing ──────────────────────────

    def _parse_paddle_result(self, result: Any) -> List[TextResult]:
        """
        Parse PaddleOCR output into a list of TextResult objects.

        PaddleOCR returns: [ [ [ [bbox_points], (text, confidence) ], ... ] ]
        The outer list has one element per image (we always pass one image).
        """
        texts: List[TextResult] = []
        if not result or result[0] is None:
            return texts

        for line in result[0]:
            if not line or len(line) < 2:
                continue
            bbox = line[0]           # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            text_info = line[1]      # (text, confidence)
            if not text_info or len(text_info) < 2:
                continue

            text: str = str(text_info[0])
            try:
                confidence = float(text_info[1])
            except (TypeError, ValueError):
                confidence = 0.0

            texts.append(
                TextResult(
                    content=text.strip(),
                    confidence=confidence,
                    bounding_box=bbox,
                )
            )
        return texts

    # ──────────────────────────────── Core pipeline ───────────────────────────

    def extract_text(
        self, image_array: np.ndarray, min_confidence: Optional[float] = None
    ) -> List[TextResult]:
        """
        Run OCR on a preprocessed numpy array and return filtered TextResults.

        :param image_array: RGB numpy array (H, W, 3) uint8.
        :param min_confidence: Override for minimum confidence threshold.
        :return: List of TextResult with confidence >= threshold.
        """
        threshold = min_confidence if min_confidence is not None else settings.OCR_MIN_CONFIDENCE
        ocr = self._get_ocr()

        if ocr is None:
            return []

        try:
            result = ocr.ocr(image_array, cls=True)
        except Exception as exc:
            logger.error("PaddleOCR inference failed: %s", exc, exc_info=True)
            return []

        texts = self._parse_paddle_result(result)
        return [t for t in texts if t.confidence >= threshold]

    def process_frame(
        self,
        base64_str: str,
        min_confidence: Optional[float] = None,
    ) -> OCRResponse:
        """
        Full pipeline: decode → preprocess → OCR → filter.

        :param base64_str: Base64-encoded image.
        :param min_confidence: Optional override for confidence threshold.
        :return: OCRResponse with results and processing time.
        """
        start = time.perf_counter()

        image_array = self.decode_frame(base64_str)
        preprocessed = self.preprocess_image(image_array)
        texts = self.extract_text(preprocessed, min_confidence)

        elapsed_ms = (time.perf_counter() - start) * 1000

        return OCRResponse(
            status="success",
            texts=texts,
            processing_time_ms=round(elapsed_ms, 2),
            engine="paddleocr",
        )
