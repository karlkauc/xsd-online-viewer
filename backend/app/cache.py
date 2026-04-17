"""In-memory LRU cache for parsed schemas with TTL eviction."""

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


class SchemaCache:
    """Thread-safe LRU + TTL cache. Small enough to keep in memory per process."""

    def __init__(self, max_entries: int, ttl_seconds: float) -> None:
        self._max_entries = max_entries
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
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return entry.value

    def put(self, key: str, value: SchemaModel) -> None:
        expires_at = time.monotonic() + self._ttl_seconds
        with self._lock:
            self._store[key] = _Entry(value=value, expires_at=expires_at)
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


schema_cache = SchemaCache(
    max_entries=settings.schema_cache_max_entries,
    ttl_seconds=settings.schema_cache_ttl_min * 60,
)
