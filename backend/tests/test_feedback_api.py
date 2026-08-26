"""POST /api/feedback stores rows via FeedbackStore; inert without a DSN."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.usage.context import UsageTracker
from app.usage.feedback import FEEDBACK_INSERT_SQL, FeedbackRow, FeedbackStore
from app.usage.recorder import UsageRecorder


class FakeCursor:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> FakeCursor:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def execute(self, sql: str, row: tuple) -> None:
        if self.conn.fail:
            raise RuntimeError("db down")
        self.conn.rows.append((sql, row))


class FakeConn:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.rows: list[tuple] = []
        self.committed = 0
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    async def commit(self) -> None:
        self.committed += 1

    async def close(self) -> None:
        self.closed = True


def make_store(fail: bool = False) -> tuple[FeedbackStore, FakeConn]:
    conn = FakeConn(fail=fail)

    async def connect(dsn: str, **kwargs):  # noqa: ANN202
        assert kwargs["password"] == "pw"
        return conn

    return FeedbackStore("postgresql://fake", "pw\n", connect=connect), conn


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.state.usage = UsageTracker(UsageRecorder("postgresql://fake"), geoip=None, hash_secret="s")
    try:
        yield TestClient(app, headers={"user-agent": "pytest-browser"})
    finally:
        del app.state.usage
        if hasattr(app.state, "feedback"):
            del app.state.feedback


def test_store_inserts_and_closes() -> None:
    import asyncio

    store, conn = make_store()
    asyncio.run(store.save(FeedbackRow(message="hi")))
    ((sql, row),) = conn.rows
    assert sql == FEEDBACK_INSERT_SQL and row[0] == "hi"
    assert conn.committed == 1 and conn.closed


def test_submit_stores_row(client: TestClient) -> None:
    store, conn = make_store()
    app.state.feedback = store
    r = client.post(
        "/api/feedback",
        json={"message": "  Diagram is great  ", "email": "a@b.co", "page": "/url", "error_detail": "x"},
    )
    assert r.status_code == 204
    ((_, row),) = conn.rows
    assert row[:5] == ("Diagram is great", "a@b.co", "/url", None, "x")
    visitor, _country, ua, device, version = row[5:]
    assert visitor and ua == "pytest-browser" and device == "desktop" and version


def test_honeypot_is_dropped_silently(client: TestClient) -> None:
    store, conn = make_store()
    app.state.feedback = store
    r = client.post("/api/feedback", json={"message": "spam", "website": "http://x"})
    assert r.status_code == 204 and conn.rows == []


def test_not_configured(client: TestClient) -> None:
    app.state.feedback = FeedbackStore("")
    r = client.post("/api/feedback", json={"message": "hi"})
    assert r.status_code == 503


def test_db_failure_is_503(client: TestClient) -> None:
    store, _ = make_store(fail=True)
    app.state.feedback = store
    r = client.post("/api/feedback", json={"message": "hi"})
    assert r.status_code == 503 and "try again" in r.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [{"message": ""}, {"message": "   "}, {"message": "x" * 4001}, {"message": "ok", "email": "nope"}],
)
def test_validation(client: TestClient, body: dict) -> None:
    app.state.feedback, _ = make_store()
    assert client.post("/api/feedback", json=body).status_code == 422
