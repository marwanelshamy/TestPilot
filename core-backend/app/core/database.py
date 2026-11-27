"""SQLAlchemy engine and session factory. Only the Core Backend has database credentials (ADR-004)."""

from collections.abc import AsyncIterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def make_engine(url: str, pool_size: int = 20, max_overflow: int = 10, pool_timeout: float = 10.0) -> Engine:
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url == "sqlite://":
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # SQLite needs this for FK enforcement
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    # Sized explicitly (QAS-1 finding): the 5 + 10 default starved 200 concurrent users. pool_timeout makes a
    # request that cannot get a connection fail fast (-> 503 SERVICE_BUSY) instead of hanging for 30 s.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=1800,
    )


def init_engine(url: str, **pool) -> Engine:
    global _engine, _SessionLocal
    _engine = make_engine(url, **pool)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    assert _engine is not None, "init_engine() not called"
    return _engine


def session_factory() -> sessionmaker[Session]:
    assert _SessionLocal is not None, "init_engine() not called"
    return _SessionLocal


async def get_session() -> AsyncIterator[Session]:
    """FastAPI dependency: one session per request; services decide when to commit.

    Deliberately an ASYNC generator (Phase 5, QAS-1 finding): FastAPI runs the clean-up of a *sync* yield
    dependency on the same worker-thread pool as the endpoints. Under load every thread was busy waiting for a
    DB connection, so the clean-ups that would return connections never ran (and were dropped when clients
    disconnected) -> all pooled connections leaked "idle in transaction" and the backend hung. An async
    generator's `finally` runs on the event loop and always returns the connection.
    """
    session = session_factory()()
    try:
        yield session
    except BaseException:  # includes cancellation when the client disconnects
        session.rollback()
        raise
    finally:
        session.close()
