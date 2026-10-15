from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import BACKEND_DIR


def build_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    kwargs: dict = {"pool_pre_ping": True}
    if url.get_backend_name() == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False}
        if not url.database or url.database == ":memory:":
            kwargs["poolclass"] = StaticPool
        else:
            database_path = Path(url.database)
            if not database_path.is_absolute():
                database_path = BACKEND_DIR / database_path
            database_path.parent.mkdir(parents=True, exist_ok=True)
            url = url.set(database=str(database_path.resolve()))
    engine = create_engine(url, **kwargs)
    if url.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session
