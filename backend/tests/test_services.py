"""
Unit tests for CacheService and FilterService.
Redis is mocked so no running Redis instance is needed.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from app.schemas import CacheStats, FilterConfig, TextResult
from app.services.cache_service import CacheService
from app.services.filter_service import FilterService


# ─────────────────────────────── Helpers ─────────────────────────────────────

def _make_cache_service(mock_redis: MagicMock) -> CacheService:
    """Return a CacheService with its internal Redis client replaced by a mock."""
    with patch("app.services.cache_service.redis_lib.Redis.from_url", return_value=mock_redis):
        svc = CacheService(redis_url="redis://localhost:6379/0")
    return svc


def _make_filter_service(mock_redis: MagicMock) -> FilterService:
    cache = _make_cache_service(mock_redis)
    return FilterService(cache_service=cache)


# ─────────────────────────────── CacheService tests ──────────────────────────

class TestCacheService:
    def test_set_and_get_session(self, mock_redis: MagicMock) -> None:
        svc = _make_cache_service(mock_redis)
        data = {"id": "abc", "title": "Test"}
        svc.set_session("abc", data, ttl=300)

        mock_redis.setex.assert_called_once_with("session:abc", 300, json.dumps(data))

        mock_redis.get.return_value = json.dumps(data)
        result = svc.get_session("abc")
        assert result == data

    def test_delete_session(self, mock_redis: MagicMock) -> None:
        svc = _make_cache_service(mock_redis)
        svc.delete_session("abc")
        mock_redis.delete.assert_called_with("session:abc")

    def test_exists_true(self, mock_redis: MagicMock) -> None:
        mock_redis.exists.return_value = 1
        svc = _make_cache_service(mock_redis)
        assert svc.exists("session:abc") is True

    def test_exists_false(self, mock_redis: MagicMock) -> None:
        mock_redis.exists.return_value = 0
        svc = _make_cache_service(mock_redis)
        assert svc.exists("session:missing") is False

    def test_get_stats_shape(self, mock_redis: MagicMock) -> None:
        mock_redis.get.side_effect = lambda k: "10" if k == "stats:hits" else "5"
        mock_redis.dbsize.return_value = 15
        mock_redis.info.return_value = {"used_memory": 2 * 1024 * 1024}

        svc = _make_cache_service(mock_redis)
        stats = svc.get_stats()

        assert isinstance(stats, CacheStats)
        assert 0.0 <= stats.hit_rate <= 1.0
        assert stats.total_keys == 15
        assert stats.memory_usage_mb > 0


# ─────────────────────────────── FilterService tests ─────────────────────────

class TestFilterService:
    def test_is_duplicate_similar(self, mock_redis: MagicMock) -> None:
        """Very similar texts should be detected as duplicates."""
        mock_redis.smembers.return_value = {"STOP"}
        svc = _make_filter_service(mock_redis)
        assert svc.is_duplicate("STOP", "session-1") is True

    def test_is_duplicate_different(self, mock_redis: MagicMock) -> None:
        """Clearly different texts should not be flagged as duplicates."""
        mock_redis.smembers.return_value = {"STOP"}
        svc = _make_filter_service(mock_redis)
        assert svc.is_duplicate("SPEED LIMIT 50", "session-1") is False

    def test_add_to_seen(self, mock_redis: MagicMock) -> None:
        svc = _make_filter_service(mock_redis)
        svc.add_to_seen("session-1", "NO ENTRY")
        mock_redis.sadd.assert_called_with("texts:session-1", "NO ENTRY")

    def test_set_and_get_keywords(self, mock_redis: MagicMock) -> None:
        svc = _make_filter_service(mock_redis)
        svc.set_keywords("session-1", ["STOP", "YIELD"], mode="include")

        # Check set was called with JSON payload
        mock_redis.set.assert_called_once()
        args = mock_redis.set.call_args[0]
        assert args[0] == "filter:session-1"
        payload = json.loads(args[1])
        assert payload["keywords"] == ["STOP", "YIELD"]
        assert payload["mode"] == "include"

        # Now simulate retrieval
        mock_redis.get.return_value = json.dumps({"keywords": ["STOP", "YIELD"], "mode": "include"})
        config = svc.get_keywords("session-1")
        assert config.keywords == ["STOP", "YIELD"]
        assert config.mode == "include"
        assert config.session_id == "session-1"

    def test_matches_filter_include_passes(self, mock_redis: MagicMock) -> None:
        mock_redis.get.return_value = json.dumps({"keywords": ["stop"], "mode": "include"})
        svc = _make_filter_service(mock_redis)
        assert svc.matches_filter("STOP sign", "session-1") is True

    def test_matches_filter_include_blocks(self, mock_redis: MagicMock) -> None:
        mock_redis.get.return_value = json.dumps({"keywords": ["stop"], "mode": "include"})
        svc = _make_filter_service(mock_redis)
        assert svc.matches_filter("YIELD sign", "session-1") is False

    def test_matches_filter_exclude_blocks(self, mock_redis: MagicMock) -> None:
        mock_redis.get.return_value = json.dumps({"keywords": ["private"], "mode": "exclude"})
        svc = _make_filter_service(mock_redis)
        assert svc.matches_filter("PRIVATE property", "session-1") is False

    def test_filter_results_removes_duplicates(self, mock_redis: MagicMock) -> None:
        # First call returns empty set (no seen texts), subsequent calls reflect sadd
        call_count = [0]
        seen: set = set()

        def fake_smembers(key):
            return seen

        def fake_sadd(key, value):
            seen.add(value)
            return 1

        mock_redis.smembers.side_effect = fake_smembers
        mock_redis.sadd.side_effect = fake_sadd
        mock_redis.get.return_value = None  # No keyword filter

        svc = _make_filter_service(mock_redis)

        texts = [
            TextResult(content="STOP", confidence=0.9, bounding_box=None),
            TextResult(content="STOP", confidence=0.88, bounding_box=None),  # Duplicate
        ]
        result = svc.filter_results(texts, "session-1")
        assert len(result) == 1
        assert result[0].content == "STOP"

    def test_filter_results_applies_keyword_filter(self, mock_redis: MagicMock) -> None:
        mock_redis.smembers.return_value = set()
        mock_redis.get.return_value = json.dumps({"keywords": ["exit"], "mode": "include"})

        svc = _make_filter_service(mock_redis)
        texts = [
            TextResult(content="EXIT", confidence=0.9, bounding_box=None),
            TextResult(content="STOP", confidence=0.85, bounding_box=None),  # Not matching
        ]
        result = svc.filter_results(texts, "session-1")
        assert len(result) == 1
        assert result[0].content == "EXIT"

    def test_filter_results_empty_list(self, mock_redis: MagicMock) -> None:
        svc = _make_filter_service(mock_redis)
        result = svc.filter_results([], "session-1")
        assert result == []

    def test_integration_set_keywords_then_filter(self, mock_redis: MagicMock) -> None:
        """Set keywords, then verify filter_results respects them."""
        stored_filter = {}

        def fake_set(key, value):
            stored_filter[key] = value

        def fake_get(key):
            return stored_filter.get(key)

        mock_redis.set.side_effect = fake_set
        mock_redis.get.side_effect = fake_get
        mock_redis.smembers.return_value = set()

        svc = _make_filter_service(mock_redis)
        svc.set_keywords("session-2", ["danger", "warning"], mode="include")

        texts = [
            TextResult(content="DANGER ZONE", confidence=0.92, bounding_box=None),
            TextResult(content="WELCOME", confidence=0.88, bounding_box=None),
        ]
        result = svc.filter_results(texts, "session-2")
        assert len(result) == 1
        assert "DANGER" in result[0].content.upper()
