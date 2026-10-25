from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, String, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator
from sqlalchemy.pool import StaticPool


DEFAULT_DATABASE_URL = "sqlite:///./data/techohub.db"


class UTCDateTime(TypeDecorator[datetime]):
    """Store UTC timestamps as canonical ISO-8601 strings in SQLite."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )

    def process_result_value(
        self, value: str | None, dialect: Any
    ) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("stored timestamps must be timezone-aware")
        return parsed.astimezone(UTC)


class Base(DeclarativeBase):
    pass


def create_database_engine(database_url: str | None = None) -> Engine:
    url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    parsed_url = make_url(url)
    connect_args: dict[str, Any] = {}
    engine_options: dict[str, Any] = {}
    if parsed_url.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
        if parsed_url.database in (None, "", ":memory:"):
            engine_options["poolclass"] = StaticPool
        if parsed_url.database not in (None, "", ":memory:"):
            Path(parsed_url.database).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(url, connect_args=connect_args, **engine_options)

    if parsed_url.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(
            dbapi_connection: Any, connection_record: Any
        ) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def database_session_dependency(
    factory: sessionmaker[Session],
) -> Generator[Session, None, None]:
    db = factory()
    try:
        yield db
    finally:
        db.close()


def utc_now() -> datetime:
    return datetime.now(UTC)
