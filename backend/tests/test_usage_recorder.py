from __future__ import annotations

import asyncio

import pytest

from app.usage.events import INSERT_SQL, UsageEvent
from app.usage.recorder import UsageRecorder


class FakeCursor:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> FakeCursor:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def executemany(self, sql: str, rows: list[tuple]) -> None:
        if self.conn.fail_times > 0:
            self.conn.fail_times -= 1
            raise RuntimeError("boom")
        assert sql == INSERT_SQL
        self.conn.rows.extend(rows)


class FakeConn:
    def __init__(self, fail_times: int = 0) -> None:
        self.rows: list[tuple] = []
        self.commits = 0
        self.closed = False
        self.fail_times = fail_times

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    async def commit(self) -> None:
        self.commits += 1

    async def close(self) -> None:
        self.closed = True


def make(fail_times: int = 0, fail_all: bool = False, **kw):
    conns: list[FakeConn] = []
    calls: list[dict] = []

    async def connect(dsn: str, **kwargs):
        calls.append({"dsn": dsn, **kwargs})
        conn = FakeConn(fail_times if (fail_all or not conns) else 0)
        conns.append(conn)
        return conn

    rec = UsageRecorder("postgresql://u@h/db", "pw\n", connect=connect, backoff_seconds=0, **kw)
    return rec, conns, calls


def test_inert_without_dsn() -> None:
    rec = UsageRecorder("")
    assert rec.enabled is False
    assert rec.record(UsageEvent(event_type="page_view")) is False


async def test_writes_batch_and_flushes_on_stop() -> None:
    rec, conns, calls = make()
    await rec.start()
    for i in range(3):
        assert rec.record(UsageEvent(event_type="page_view", path=f"/{i}"))
    await rec.stop()
    assert len(conns) == 1
    assert [r[7] for r in conns[0].rows] == ["/0", "/1", "/2"]
    assert conns[0].commits >= 1
    assert conns[0].closed is True
    assert calls[0]["password"] == "pw" and calls[0]["dsn"] == "postgresql://u@h/db"
    assert rec.written == 3


async def test_retries_then_succeeds_on_new_connection() -> None:
    rec, conns, _ = make(fail_times=1)
    await rec.start()
    rec.record(UsageEvent(event_type="export", source="html"))
    await rec.stop()
    assert len(conns) == 2  # first connection discarded after the failure
    assert conns[0].closed and len(conns[1].rows) == 1
    assert rec.dropped == 0


async def test_drops_after_max_attempts() -> None:
    rec, conns, _ = make(fail_times=99, fail_all=True, max_attempts=2)
    await rec.start()
    rec.record(UsageEvent(event_type="export"))
    await rec.stop()
    assert rec.dropped == 1 and rec.written == 0


async def test_queue_full_drops() -> None:
    rec, _, _ = make(queue_size=1)
    # not started: nothing drains the queue
    assert rec.record(UsageEvent(event_type="page_view")) is True
    assert rec.record(UsageEvent(event_type="page_view")) is False
    assert rec.dropped == 1


async def test_stop_timeout_does_not_hang() -> None:
    async def hang(dsn: str, **kw):
        await asyncio.sleep(10)

    rec = UsageRecorder("postgresql://u@h/db", connect=hang, backoff_seconds=0)
    await rec.start()
    rec.record(UsageEvent(event_type="page_view"))
    await asyncio.sleep(0)
    await rec.stop(timeout=0.05)
    assert rec._worker is None


@pytest.mark.parametrize("enabled", [False])
async def test_start_noop_when_disabled(enabled: bool) -> None:
    rec = UsageRecorder("")
    await rec.start()
    await rec.stop()
    assert rec._worker is None


async def test_drain_waits_for_write() -> None:
    rec, conns, _ = make()
    await rec.start()
    assert await rec.drain() is True  # nothing pending
    rec.record(UsageEvent(event_type="page_view"))
    assert await rec.drain(timeout=1.0) is True
    assert len(conns[0].rows) == 1
    await rec.stop()


async def test_drain_times_out_on_hanging_connection() -> None:
    async def hang(dsn: str, **kw):
        await asyncio.sleep(10)

    rec = UsageRecorder("postgresql://u@h/db", connect=hang, backoff_seconds=0)
    await rec.start()
    rec.record(UsageEvent(event_type="page_view"))
    assert await rec.drain(timeout=0.05) is False
    await rec.stop(timeout=0.05)


def test_drain_noop_when_not_started() -> None:
    rec = UsageRecorder("")
    assert asyncio.run(rec.drain()) is True
