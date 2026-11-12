"""Tests for backend.database engine creation and configuration.

These tests verify the database engine is configured correctly for both local
SQLite development and production PostgreSQL (Neon) without requiring a real
PostgreSQL connection. SQLAlchemy's create_engine does not connect until the
first use, so the dialect, connect arguments and pool options can be inspected
by monkeypatching create_engine.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.schema import CreateTable

from backend.database import (
    DEFAULT_DATABASE_URL,
    Base,
    create_database_engine,
    is_postgresql_url,
)
from backend import models as _models  # noqa: F401


def _capture_create_engine(monkeypatch):
    captured: dict[str, object] = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["connect_args"] = kwargs.get("connect_args", {})
        captured["engine_options"] = {
            k: v
            for k, v in kwargs.items()
            if k not in ("connect_args",)
        }
        # Return a real in-memory SQLite engine so callers can still use it.
        return create_engine("sqlite:///:memory:")

    monkeypatch.setattr("backend.database.create_engine", fake_create_engine)
    return captured


def test_is_postgresql_url_detects_postgres_variants() -> None:
    assert is_postgresql_url("postgresql+psycopg://user:pass@host/db") is True
    assert is_postgresql_url("postgres://user:pass@host/db") is True
    assert is_postgresql_url("postgresql+psycopg://host/db?sslmode=require") is True
    assert is_postgresql_url("sqlite:///./data/techohub.db") is False
    assert is_postgresql_url("sqlite:///:memory:") is False


def test_postgresql_urls_use_psycopg_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_create_engine(monkeypatch)

    create_database_engine("postgres://user:pass@ep-xyz.aws.neon.tech/db")

    assert make_url(str(captured["url"])).drivername == "postgresql+psycopg"


def test_sqlite_default_uses_local_database(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_create_engine(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    engine = create_database_engine()
    assert engine is not None
    assert str(captured["url"]) == DEFAULT_DATABASE_URL
    assert captured["connect_args"].get("check_same_thread") is False


def test_postgresql_url_configures_tls_and_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_create_engine(monkeypatch)
    pg_url = (
        "postgresql+psycopg://user:pass@ep-xyz.aws.neon.tech/db?sslmode=require"
    )
    engine = create_database_engine(pg_url)
    assert engine is not None
    assert str(captured["url"]).startswith("postgresql+psycopg://")
    # Neon requires TLS.
    assert captured["connect_args"].get("sslmode") == "require"
    # Serverless-friendly pool: small, pre-ping, no overflow.
    opts = captured["engine_options"]
    assert opts.get("pool_pre_ping") is True
    assert opts.get("pool_size") == 1
    assert opts.get("max_overflow") == 0


@pytest.mark.parametrize(
    ("query", "expected_sslmode"),
    [("sslmode=verify-full", "verify-full"), ("sslmode=disable", "require")],
)
def test_postgresql_url_requires_tls_without_downgrading_verification(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
    expected_sslmode: str,
) -> None:
    captured = _capture_create_engine(monkeypatch)

    create_database_engine(f"postgresql://user:pass@host/db?{query}")

    assert captured["connect_args"]["sslmode"] == expected_sslmode


def test_database_url_env_var_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_create_engine(monkeypatch)
    pg_url = "postgresql://user:pass@ep-xyz.aws.neon.tech/db"
    monkeypatch.setenv("DATABASE_URL", pg_url)
    create_database_engine()
    assert make_url(str(captured["url"])).drivername == "postgresql+psycopg"


def test_database_url_argument_takes_precedence_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_create_engine(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///env.sqlite3")
    create_database_engine("postgresql+psycopg://user:pass@host/db")
    assert make_url(str(captured["url"])).drivername == "postgresql+psycopg"


def test_creates_an_engine_instance() -> None:
    engine = create_database_engine("sqlite:///:memory:")
    assert isinstance(engine, Engine)


def test_postgresql_engine_loads_psycopg_without_connecting() -> None:
    engine = create_database_engine("postgresql://user:pass@host/db")
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_engine_credential_not_in_repr() -> None:
    pg_url = "postgresql+psycopg://secret-user:secret-pass@host/db"
    text = str(make_url(pg_url))
    assert "secret-pass" not in text
    assert "***" in text


def test_metadata_compiles_using_postgresql_dialect() -> None:
    statements = [
        str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for table in Base.metadata.sorted_tables
    ]
    assert len(statements) == len(Base.metadata.tables)
    assert all("CREATE TABLE" in statement for statement in statements)
    assert all("AUTOINCREMENT" not in statement for statement in statements)


def test_create_app_requires_database_url_on_vercel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.main import create_app

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required on Vercel"):
        create_app()


def test_create_app_succeeds_locally_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.main import create_app

    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app()
    assert app is not None
    assert str(app.state.database_engine.url) == DEFAULT_DATABASE_URL


def test_create_app_rejects_sqlite_database_on_vercel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.main import create_app

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    with pytest.raises(RuntimeError, match="valid PostgreSQL connection string"):
        create_app()


def test_invalid_vercel_database_url_does_not_echo_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.main import create_app

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv(
        "DATABASE_URL",
        "not a url containing secret-password",
    )

    with pytest.raises(RuntimeError) as error:
        create_app()

    assert "secret-password" not in str(error.value)


def test_create_app_succeeds_on_vercel_with_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import create_engine as real_create_engine

    from backend.main import create_app

    monkeypatch.setattr(
        "backend.database.create_engine",
        lambda url, **kwargs: real_create_engine("sqlite:///:memory:"),
    )
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("TECHOHUB_RAG_ENABLED", raising=False)
    monkeypatch.delenv("TECHOHUB_RAG_PROVIDER", raising=False)
    monkeypatch.delenv("TECHOHUB_MCP_ENABLED", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:pass@ep-xyz.aws.neon.tech/db?sslmode=require",
    )
    app = create_app()
    assert app is not None


def test_vercel_disables_semantic_rag_and_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import create_engine as real_create_engine

    from backend.main import create_app

    monkeypatch.setattr(
        "backend.database.create_engine",
        lambda url, **kwargs: real_create_engine("sqlite:///:memory:"),
    )
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:pass@ep-xyz.aws.neon.tech/db?sslmode=require",
    )
    monkeypatch.setenv("TECHOHUB_RAG_ENABLED", "true")
    monkeypatch.setenv("TECHOHUB_RAG_PROVIDER", "semantic")
    monkeypatch.setenv("TECHOHUB_MCP_ENABLED", "true")

    workflow = create_app().state.conversation_workflow

    assert workflow._rag_provider == "lexical"
    assert workflow._semantic_retriever is None
    assert workflow._mcp_enabled is False


def test_cors_rejects_wildcard_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.main import _cors_allow_origins

    monkeypatch.setenv("TECHOHUB_CORS_ORIGINS", "*")

    with pytest.raises(ValueError, match="must not contain a wildcard"):
        _cors_allow_origins()
