"""In-memory LRU cache for parsed schemas, evicted after a TTL of disuse."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock

from app.config import settings
from app.parser.model import SchemaModel


@dataclass
class _Entry:
    value: SchemaModel
    expires_at: float
    size: int = 0


class SchemaCache:
    """Thread-safe LRU + TTL cache. Small enough to keep in memory per process."""

    def __init__(self, max_entries: int, ttl_seconds: float, max_bytes: int = 0) -> None:
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._bytes = 0
        self._ttl_seconds = ttl_seconds
        self._store: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> SchemaModel | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._drop(key)
                return None
            # Sliding expiry: a schema someone is still working with stays.
            entry.expires_at = now + self._ttl_seconds
            self._store.move_to_end(key)
            return entry.value

    def put(self, key: str, value: SchemaModel, size: int = 0) -> None:
        """Store ``value``; ``size`` is its approximate memory footprint in bytes."""
        expires_at = time.monotonic() + self._ttl_seconds
        with self._lock:
            self._drop(key)
            self._store[key] = _Entry(value=value, expires_at=expires_at, size=size)
            self._bytes += size
            # Oldest first; the entry just stored stays even if it alone is over budget.
            while len(self._store) > 1 and (
                len(self._store) > self._max_entries or (self._max_bytes and self._bytes > self._max_bytes)
            ):
                self._drop(next(iter(self._store)))

    def _drop(self, key: str) -> None:
        entry = self._store.pop(key, None)
        if entry is not None:
            self._bytes -= entry.size

    def delete(self, key: str) -> None:
        with self._lock:
            self._drop(key)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._bytes = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


schema_cache = SchemaCache(
    max_entries=settings.schema_cache_max_entries,
    ttl_seconds=settings.schema_cache_ttl_min * 60,
    max_bytes=settings.cache_max_mb * 1024 * 1024,
)
