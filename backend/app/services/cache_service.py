"""
CacheService — Redis-backed cache for session metadata and seen-texts deduplication.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import redis as redis_lib

from app.config import settings
from app.schemas import CacheStats

logger = logging.getLogger(__name__)

# Key prefixes
_SESSION_PREFIX = "session:"
_TEXTS_PREFIX = "texts:"
_HIT_COUNTER_KEY = "stats:hits"
_MISS_COUNTER_KEY = "stats:misses"


class CacheService:
    """
    Thin wrapper around redis-py providing typed methods for the SignReader
    session cache and seen-texts set.
    """

    def __init__(self, redis_url: Optional[str] = None) -> None:
        url = redis_url or settings.REDIS_URL
        self._client: redis_lib.Redis = redis_lib.Redis.from_url(
            url, decode_responses=True
        )

    # ──────────────────────────────── Session metadata ────────────────────────

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return cached session dict or None if not cached."""
        key = f"{_SESSION_PREFIX}{session_id}"
        raw = self._client.get(key)
        if raw is None:
            self._client.incr(_MISS_COUNTER_KEY)
            return None
        self._client.incr(_HIT_COUNTER_KEY)
        return json.loads(raw)

    def set_session(
        self, session_id: str, data: Dict[str, Any], ttl: int = 300
    ) -> None:
        """Cache session data for *ttl* seconds (default 5 minutes)."""
        key = f"{_SESSION_PREFIX}{session_id}"
        self._client.setex(key, ttl, json.dumps(data))

    def delete_session(self, session_id: str) -> None:
        """Remove the cached session entry."""
        self._client.delete(f"{_SESSION_PREFIX}{session_id}")

    # ──────────────────────────────── Seen texts ─────────────────────────────

    def get_texts(self, session_id: str) -> List[str]:
        """Return all seen texts for a session (stored as a Redis Set)."""
        key = f"{_TEXTS_PREFIX}{session_id}"
        members = self._client.smembers(key)
        return list(members) if members else []

    def add_text(self, session_id: str, text: str, ttl: int = 3600) -> None:
        """Add *text* to the seen-texts set for *session_id*."""
        key = f"{_TEXTS_PREFIX}{session_id}"
        self._client.sadd(key, text)
        # Refresh TTL each time a new text is added
        self._client.expire(key, ttl)

    # ──────────────────────────────── Utilities ───────────────────────────────

    def exists(self, key: str) -> bool:
        """Return True if *key* exists in Redis."""
        return bool(self._client.exists(key))

    def clear_all_session_data(self, session_id: str) -> None:
        """Delete both session metadata and seen-texts for a session."""
        self._client.delete(
            f"{_SESSION_PREFIX}{session_id}",
            f"{_TEXTS_PREFIX}{session_id}",
        )

    # ──────────────────────────────── Stats ──────────────────────────────────

    def get_stats(self) -> CacheStats:
        """
        Return cache statistics.

        hit_rate is computed from the running hit/miss counters.
        total_keys is from Redis DBSIZE (all keys in current DB).
        memory_usage_mb from Redis INFO memory.
        """
        try:
            hits = int(self._client.get(_HIT_COUNTER_KEY) or 0)
            misses = int(self._client.get(_MISS_COUNTER_KEY) or 0)
            total_ops = hits + misses
            hit_rate = (hits / total_ops) if total_ops > 0 else 0.0

            total_keys = self._client.dbsize()

            info = self._client.info("memory")
            used_memory_bytes = int(info.get("used_memory", 0))
            memory_mb = used_memory_bytes / (1024 * 1024)

            return CacheStats(
                hit_rate=round(hit_rate, 4),
                total_keys=total_keys,
                memory_usage_mb=round(memory_mb, 4),
            )
        except redis_lib.RedisError as exc:
            logger.error("Failed to fetch cache stats: %s", exc)
            return CacheStats(hit_rate=0.0, total_keys=0, memory_usage_mb=0.0)
