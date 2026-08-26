"""Fire-and-forget writer for usage events.

Events are queued in memory and written by a single background task over
one psycopg async connection. Nothing here may ever raise into a request
handler: failures are logged (rate-limited) and the event is dropped.

Inert when constructed without a DSN — ``record()`` then simply returns
False, which keeps local dev and the test suite free of any DB dependency.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.usage.events import INSERT_SQL, UsageEvent

logger = logging.getLogger(__name__)

ConnectFn = Callable[..., Awaitable[Any]]

_STOP = object()


async def _default_connect(dsn: str, **kwargs: Any) -> Any:
    import psycopg  # imported lazily so an unconfigured app never loads libpq

    return await psycopg.AsyncConnection.connect(dsn, **kwargs)


class UsageRecorder:
    def __init__(
        self,
        dsn: str,
        password: str = "",
        *,
        connect: ConnectFn = _default_connect,
        queue_size: int = 1000,
        batch_size: int = 50,
        max_attempts: int = 3,
        backoff_seconds: float = 1.5,
        connect_timeout: int = 5,
        warn_interval_seconds: float = 60.0,
    ) -> None:
        self._dsn = dsn.strip()
        # Secret-manager values often carry a trailing newline; never let that break auth.
        self._password = password.strip("\r\n")
        self._connect = connect
        self._queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=queue_size)
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._connect_timeout = connect_timeout
        self._warn_interval = warn_interval_seconds
        self._last_warn = 0.0
        self._conn: Any = None
        self._worker: asyncio.Task[None] | None = None
        self._pending = 0
        self._idle: asyncio.Event | None = None
        self.dropped = 0
        self.written = 0

    @property
    def enabled(self) -> bool:
        return bool(self._dsn)

    # -- public API ---------------------------------------------------------

    def record(self, event: UsageEvent) -> bool:
        """Enqueue without blocking. Returns False if disabled or dropped."""
        if not self.enabled:
            return False
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1
            self._warn("usage queue full, dropping event")
            return False
        self._pending += 1
        if self._idle is not None:
            self._idle.clear()
        return True

    async def drain(self, timeout: float = 2.0) -> bool:
        """Wait (bounded) until every queued event has been written or dropped.

        Called by the request middleware after a handler emitted events: on
        Cloud Run the CPU is throttled once the response is sent, so a purely
        background writer may starve. Returns True when the queue is idle.
        """
        if self._worker is None or self._idle is None or self._pending == 0:
            return True
        try:
            await asyncio.wait_for(self._idle.wait(), timeout=timeout)
        except asyncio.TimeoutError:  # noqa: UP041 - py3.10 local dev
            return False
        return True

    async def start(self) -> None:
        if not self.enabled or self._worker is not None:
            return
        self._idle = asyncio.Event()
        if self._pending == 0:
            self._idle.set()
        self._worker = asyncio.create_task(self._run(), name="usage-recorder")
        logger.info("usage recorder started")

    async def stop(self, timeout: float = 5.0) -> None:
        """Flush what is queued (bounded by ``timeout``) and close the connection."""
        if self._worker is None:
            return
        await self._queue.put(_STOP)
        try:
            await asyncio.wait_for(self._worker, timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):  # noqa: UP041 - py3.10 local dev
            self._worker.cancel()
            self._warn("usage recorder stop timed out; pending events lost")
        finally:
            self._worker = None
            await self._close()

    # -- worker -------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            first = await self._queue.get()
            if first is _STOP:
                return
            batch = [first]
            stop_after = False
            while len(batch) < self._batch_size:
                try:
                    item = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if item is _STOP:
                    stop_after = True
                    break
                batch.append(item)
            try:
                await self._write_with_retry(batch)
            finally:
                self._pending = max(0, self._pending - len(batch))
                if self._pending == 0 and self._idle is not None:
                    self._idle.set()
            if stop_after:
                return

    async def _write_with_retry(self, batch: list[UsageEvent]) -> None:
        rows = [e.as_row() for e in batch]
        for attempt in range(1, self._max_attempts + 1):
            try:
                await self._write(rows)
                self.written += len(rows)
                return
            except Exception as exc:  # noqa: BLE001 - never propagate
                await self._close()
                if attempt == self._max_attempts:
                    self.dropped += len(rows)
                    self._warn(f"usage insert failed after {attempt} attempts, dropping {len(rows)}: {exc!r}")
                    return
                await asyncio.sleep(self._backoff * attempt)

    async def _write(self, rows: list[tuple]) -> None:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.executemany(INSERT_SQL, rows)
        await conn.commit()

    async def _connection(self) -> Any:
        if self._conn is None or getattr(self._conn, "closed", False):
            kwargs: dict[str, Any] = {"connect_timeout": self._connect_timeout, "autocommit": False}
            if self._password:
                kwargs["password"] = self._password
            self._conn = await self._connect(self._dsn, **kwargs)
        return self._conn

    async def _close(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            with contextlib.suppress(Exception):
                await conn.close()

    def _warn(self, message: str) -> None:
        now = time.monotonic()
        if now - self._last_warn >= self._warn_interval:
            self._last_warn = now
            logger.warning(message, extra={"ctx_dropped": self.dropped, "ctx_written": self.written})
