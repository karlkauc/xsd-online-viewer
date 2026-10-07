"""Tests for the in-memory schema cache."""

from __future__ import annotations

from unittest.mock import patch

from app.cache import SchemaCache
from app.parser.model import SchemaModel


def _model(name: str) -> SchemaModel:
    return SchemaModel(schema_id=name)


def test_expires_after_the_ttl_of_disuse() -> None:
    cache = SchemaCache(max_entries=4, ttl_seconds=60)
    with patch("app.cache.time.monotonic", return_value=0.0):
        cache.put("a", _model("a"))
    with patch("app.cache.time.monotonic", return_value=61.0):
        assert cache.get("a") is None


def test_use_extends_the_ttl() -> None:
    # A schema loaded an hour ago and validated against ever since must not
    # vanish mid-session ("schema not found or expired").
    cache = SchemaCache(max_entries=4, ttl_seconds=60)
    with patch("app.cache.time.monotonic", return_value=0.0):
        cache.put("a", _model("a"))
    with patch("app.cache.time.monotonic", return_value=50.0):
        assert cache.get("a") is not None
    with patch("app.cache.time.monotonic", return_value=100.0):
        assert cache.get("a") is not None
    with patch("app.cache.time.monotonic", return_value=161.0):
        assert cache.get("a") is None


def test_least_recently_used_entry_is_evicted() -> None:
    cache = SchemaCache(max_entries=2, ttl_seconds=60)
    cache.put("a", _model("a"))
    cache.put("b", _model("b"))
    assert cache.get("a") is not None
    cache.put("c", _model("c"))
    assert cache.get("b") is None
    assert cache.get("a") is not None and cache.get("c") is not None
