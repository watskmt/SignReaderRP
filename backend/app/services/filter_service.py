"""
FilterService — fuzzy deduplication and keyword-based filtering for OCR results.
"""
from __future__ import annotations

import difflib
import json
import logging
from typing import List, Optional

from app.schemas import FilterConfig, TextResult
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

# Redis key prefix for keyword filter configuration
_FILTER_PREFIX = "filter:"


class FilterService:
    """
    Provides two filtering capabilities:

    1. Deduplication — uses difflib.SequenceMatcher to detect near-duplicate
       texts within a session (threshold configurable, default 0.85).
    2. Keyword filtering — per-session include/exclude keyword lists stored
       in Redis.
    """

    def __init__(
        self,
        cache_service: Optional[CacheService] = None,
        dedup_threshold: float = 0.85,
    ) -> None:
        self._cache = cache_service or CacheService()
        self._dedup_threshold = dedup_threshold

    # ──────────────────────────────── Deduplication ───────────────────────────

    def is_duplicate(
        self,
        text: str,
        session_id: str,
        threshold: Optional[float] = None,
    ) -> bool:
        """
        Return True if *text* is similar to any previously seen text for this session.

        Similarity is measured with difflib.SequenceMatcher.ratio(). A ratio
        >= *threshold* is considered a duplicate.
        """
        limit = threshold if threshold is not None else self._dedup_threshold
        seen_texts = self._cache.get_texts(session_id)
        text_lower = text.lower().strip()

        for seen in seen_texts:
            ratio = difflib.SequenceMatcher(
                None, text_lower, seen.lower().strip()
            ).ratio()
            if ratio >= limit:
                return True
        return False

    def add_to_seen(self, session_id: str, text: str, ttl: int = 3600) -> None:
        """Record *text* as seen for *session_id* so future duplicates are detected."""
        self._cache.add_text(session_id, text, ttl=ttl)

    # ──────────────────────────────── Keyword filter ─────────────────────────

    def set_keywords(
        self, session_id: str, keywords: List[str], mode: str = "include"
    ) -> None:
        """
        Persist keyword filter configuration for a session.

        :param mode: "include" — only keep texts that contain a keyword.
                     "exclude" — drop texts that contain a keyword.
        """
        config = {"keywords": keywords, "mode": mode}
        key = f"{_FILTER_PREFIX}{session_id}"
        self._cache._client.set(key, json.dumps(config))

    def get_keywords(self, session_id: str) -> FilterConfig:
        """
        Retrieve the keyword filter configuration for a session.
        Returns an empty include-filter if none is set.
        """
        key = f"{_FILTER_PREFIX}{session_id}"
        raw = self._cache._client.get(key)
        if raw is None:
            return FilterConfig(session_id=session_id, keywords=[], mode="include")
        data = json.loads(raw)
        return FilterConfig(
            session_id=session_id,
            keywords=data.get("keywords", []),
            mode=data.get("mode", "include"),
        )

    def matches_filter(self, text: str, session_id: str) -> bool:
        """
        Return True if *text* should be kept after applying the keyword filter.

        - include mode with keywords: text must contain at least one keyword.
        - include mode with no keywords: all texts pass.
        - exclude mode with keywords: text must NOT contain any keyword.
        - exclude mode with no keywords: all texts pass.
        """
        config = self.get_keywords(session_id)
        if not config.keywords:
            return True

        text_lower = text.lower()
        keyword_match = any(kw.lower() in text_lower for kw in config.keywords)

        if config.mode == "include":
            return keyword_match
        # exclude mode
        return not keyword_match

    # ──────────────────────────────── Combined pipeline ───────────────────────

    def filter_results(
        self, texts: List[TextResult], session_id: str
    ) -> List[TextResult]:
        """
        Apply deduplication and keyword filtering to a list of TextResults.

        Texts that are duplicates OR that fail the keyword filter are removed.
        Unique, passing texts are added to the seen-texts set.
        """
        if not texts:
            return []

        kept: List[TextResult] = []
        seen_this_batch: List[str] = []

        for result in texts:
            # Check against previously seen texts in Redis AND within this batch
            is_dup = self.is_duplicate(result.content, session_id)
            if not is_dup:
                # Also check within the current batch (before they're flushed to Redis)
                text_lower = result.content.lower().strip()
                for batch_text in seen_this_batch:
                    ratio = difflib.SequenceMatcher(
                        None, text_lower, batch_text.lower()
                    ).ratio()
                    if ratio >= self._dedup_threshold:
                        is_dup = True
                        break

            if is_dup:
                continue

            if not self.matches_filter(result.content, session_id):
                continue

            kept.append(result)
            seen_this_batch.append(result.content)

        return kept
