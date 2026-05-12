"""
GeminiService — validates OCR-recognized text using Gemini API.

Sends batched text to Gemini to determine whether each string looks
like real sign/notice text versus OCR noise or garbled characters.
Results are cached in Redis to avoid re-querying the same text.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
あなたは日本の看板・標識・掲示物の写真からOCRで認識されたテキストを検証するシステムです。

以下の各テキストについて、実際の看板や文書に存在しそうな文字列かどうかを判定してください。

判定基準:
- 実在する (is_real=true): 日本語の単語、数字、住所、日付、電話番号、英単語、記号の組み合わせとして意味を持つもの
- 実在しない (is_real=false): ランダムな文字の羅列、OCRノイズ、単一の記号、意味をなさない文字列

テキスト一覧 (JSON配列):
{texts_json}

各テキストについて以下のJSON配列を返してください（テキストの順序を保持）:
[{{"text": "...", "is_real": true/false, "probability": 0.0~1.0}}]

JSONのみ返してください。説明は不要です。"""


class GeminiService:
    def __init__(self) -> None:
        self._model: Optional[object] = None
        self._cache: Optional[object] = None

    def _get_model(self) -> Optional[object]:
        if self._model is not None:
            return self._model
        if not settings.GEMINI_API_KEY:
            return None
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self._model = genai.GenerativeModel(settings.GEMINI_MODEL)
            logger.info("Gemini model '%s' ready.", settings.GEMINI_MODEL)
        except Exception as exc:
            logger.warning("Failed to initialise Gemini: %s", exc)
            self._model = None
        return self._model

    def _get_cache(self) -> Optional[object]:
        if self._cache is not None:
            return self._cache
        try:
            from app.services.cache_service import CacheService
            self._cache = CacheService()
        except Exception:
            pass
        return self._cache

    def _cache_key(self, text: str) -> str:
        return f"gemini:valid:{text[:80]}"

    def _cached_result(self, text: str) -> Optional[bool]:
        cache = self._get_cache()
        if cache is None:
            return None
        try:
            raw = cache._client.get(self._cache_key(text))
            if raw is not None:
                return json.loads(raw)
        except Exception:
            pass
        return None

    def _set_cache(self, text: str, is_real: bool) -> None:
        cache = self._get_cache()
        if cache is None:
            return
        try:
            cache._client.set(self._cache_key(text), json.dumps(is_real), ex=86400)
        except Exception:
            pass

    def validate_texts(self, texts: List[str]) -> List[bool]:
        """Return a list of booleans indicating whether each text is real.

        Falls back to True (keep all) on any error so OCR results are
        never silently dropped due to Gemini unavailability.
        """
        if not texts:
            return []

        model = self._get_model()
        if model is None:
            return [True] * len(texts)

        # Check cache first
        results: List[Optional[bool]] = [self._cached_result(t) for t in texts]
        uncached_indices = [i for i, r in enumerate(results) if r is None]

        if not uncached_indices:
            return [bool(r) for r in results]

        uncached_texts = [texts[i] for i in uncached_indices]

        try:
            prompt = _PROMPT_TEMPLATE.format(
                texts_json=json.dumps(uncached_texts, ensure_ascii=False)
            )
            response = model.generate_content(prompt)
            raw = response.text.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            validated = json.loads(raw)

            for idx, item in zip(uncached_indices, validated):
                prob = float(item.get("probability", 0.0))
                is_real = prob >= settings.GEMINI_MIN_PROBABILITY
                results[idx] = is_real
                self._set_cache(texts[idx], is_real)

            logger.info(
                "Gemini validated %d texts: %d kept, %d discarded",
                len(uncached_texts),
                sum(1 for r in results if r),
                sum(1 for r in results if not r),
            )

        except Exception as exc:
            logger.warning("Gemini validation failed, keeping all texts: %s", exc)
            for idx in uncached_indices:
                results[idx] = True

        return [bool(r) for r in results]
