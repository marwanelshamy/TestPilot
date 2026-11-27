"""Regression tests for the QAS-1 finding (Phase 5): DB sessions must always be returned, and an exhausted
pool must be answered with a clear 503, never by hanging the whole backend."""

import asyncio

import pytest
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core import database


class SpySession:
    def __init__(self):
        self.closed = self.rolled_back = False

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture
def spy(monkeypatch):
    s = SpySession()
    monkeypatch.setattr(database, "session_factory", lambda: lambda: s)
    return s


def test_dependency_runs_on_the_event_loop():
    # a sync generator's clean-up would compete with the endpoints for worker threads (the leak)
    import inspect

    assert inspect.isasyncgenfunction(database.get_session)


def drive(gen_fn, throw=None):
    async def run():
        agen = gen_fn()
        await agen.__anext__()
        if throw is None:  # normal end of request: FastAPI resumes the generator after the response
            with pytest.raises(StopAsyncIteration):
                await agen.__anext__()
        else:
            with pytest.raises(type(throw)):
                await agen.athrow(throw)

    asyncio.run(run())


def test_session_closed_after_success(spy):
    drive(database.get_session)
    assert spy.closed and not spy.rolled_back


def test_session_rolled_back_and_closed_on_error(spy):
    drive(database.get_session, RuntimeError("boom"))
    assert spy.rolled_back and spy.closed


def test_session_closed_when_client_disconnects(spy):
    drive(database.get_session, asyncio.CancelledError())
    assert spy.rolled_back and spy.closed


def test_exhausted_pool_is_a_clean_503(client, dev, monkeypatch):
    def no_connection(*a, **k):
        raise PoolTimeoutError("QueuePool limit reached")

    monkeypatch.setattr("app.services.project_service.ProjectService.list_projects", no_connection)
    r = client.get("/api/projects", headers=dev)
    assert r.status_code == 503 and r.json()["error"]["code"] == "SERVICE_BUSY"
    assert client.get("/api/health").status_code == 200  # the backend itself stays responsive


def test_postgres_pool_is_sized_explicitly():
    eng = database.make_engine(
        "postgresql+psycopg://u:p@localhost:5432/x", pool_size=20, max_overflow=10, pool_timeout=10
    )
    assert (eng.pool.size(), eng.pool._max_overflow, eng.pool._timeout) == (20, 10, 10)
