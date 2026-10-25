from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.main import create_app
from backend.models import AuditEvent, ConversationSession, Message
from backend.session_service import ASSISTANT_DISCLOSURE, INTERIM_RESPONSE


def _message_payload(session_id: str) -> dict[str, object]:
    return {
        "session_id": session_id,
        "trace_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "channel_type": "text_web",
        "modality": "text",
        "message_text": "TEST ONLY: What are your hours?",
    }


def test_api_start_message_status_and_end_lifecycle(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'api.sqlite3').as_posix()}")
    with TestClient(app) as client:
        started = client.post("/api/sessions", json={"channel_type": "text_web"})
        assert started.status_code == 201
        start_payload = started.json()
        session_id = start_payload["session"]["session_id"]

        assert start_payload["session"]["status"] == "active"
        assert start_payload["session"]["message_count"] == 1
        assert start_payload["assistant_disclosure"] == ASSISTANT_DISCLOSURE

        sent = client.post(
            f"/api/sessions/{session_id}/messages",
            json=_message_payload(session_id),
        )
        assert sent.status_code == 200
        message_payload = sent.json()
        assert message_payload["customer_message"]["text"] == (
            "TEST ONLY: What are your hours?"
        )
        assert message_payload["assistant_message"]["text"] == INTERIM_RESPONSE

        status_response = client.get(f"/api/sessions/{session_id}")
        assert status_response.status_code == 200
        assert status_response.json()["message_count"] == 3
        assert status_response.json()["audit_event_count"] == 3
        assert "messages" not in status_response.json()

        ended = client.post(
            f"/api/sessions/{session_id}/end",
            json={"outcome": "unresolved"},
        )
        assert ended.status_code == 200
        assert ended.json()["status"] == "closed"
        assert ended.json()["outcome"] == "unresolved"
        assert ended.json()["ended_at"] is not None

        with app.state.session_factory() as db:
            session = db.get(ConversationSession, session_id)
            assert session is not None
            messages = list(
                db.scalars(
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.sequence)
                )
            )
            audits = list(
                db.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.session_id == session_id)
                    .order_by(AuditEvent.timestamp, AuditEvent.action)
                )
            )

        assert len(messages) == 3
        assert [message.sequence for message in messages] == [1, 2, 3]
        assert {event.action for event in audits} == {
            "session.started",
            "message.received",
            "assistant.response_pending",
            "session.ended",
        }


def test_api_returns_404_for_unknown_session(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'unknown.sqlite3').as_posix()}")
    unknown_id = str(uuid4())
    with TestClient(app) as client:
        assert client.get(f"/api/sessions/{unknown_id}").status_code == 404
        assert (
            client.post(
                f"/api/sessions/{unknown_id}/messages",
                json=_message_payload(unknown_id),
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/sessions/{unknown_id}/end",
                json={"outcome": "unresolved"},
            ).status_code
            == 404
        )


def test_api_rejects_invalid_ids_and_payloads(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'invalid.sqlite3').as_posix()}")
    with TestClient(app) as client:
        assert client.get("/api/sessions/not-a-uuid").status_code == 422
        assert client.post("/api/sessions", json={"channel_type": "unknown"}).status_code == 422
        assert client.post("/api/sessions", json={"channel_type": "telephony"}).status_code == 422

        started = client.post("/api/sessions", json={})
        session_id = started.json()["session"]["session_id"]
        invalid_message = _message_payload(session_id)
        invalid_message["message_text"] = " "
        assert (
            client.post(
                f"/api/sessions/{session_id}/messages",
                json=invalid_message,
            ).status_code
            == 422
        )


def test_api_rejects_mismatched_and_wrong_channel_message(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'mismatch.sqlite3').as_posix()}")
    with TestClient(app) as client:
        started = client.post("/api/sessions", json={"channel_type": "text_web"})
        session_id = started.json()["session"]["session_id"]

        mismatch = client.post(
            f"/api/sessions/{session_id}/messages",
            json=_message_payload(str(uuid4())),
        )
        assert mismatch.status_code == 422

        wrong_channel = _message_payload(session_id)
        wrong_channel["channel_type"] = "browser_voice"
        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json=wrong_channel,
        )
        assert response.status_code == 422


def test_api_rejects_message_after_close_and_duplicate_end(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'closed.sqlite3').as_posix()}")
    with TestClient(app) as client:
        started = client.post("/api/sessions", json={})
        session_id = started.json()["session"]["session_id"]

        ended = client.post(
            f"/api/sessions/{session_id}/end",
            json={"outcome": "cancelled"},
        )
        assert ended.status_code == 200

        message_result = client.post(
            f"/api/sessions/{session_id}/messages",
            json=_message_payload(session_id),
        )
        assert message_result.status_code == 409

        duplicate_end = client.post(
            f"/api/sessions/{session_id}/end",
            json={"outcome": "cancelled"},
        )
        assert duplicate_end.status_code == 409


def test_status_endpoint_does_not_expose_transcript(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'status.sqlite3').as_posix()}")
    with TestClient(app) as client:
        started = client.post("/api/sessions", json={})
        session_id = started.json()["session"]["session_id"]
        response = client.get(f"/api/sessions/{session_id}")

    assert response.status_code == 200
    assert "messages" not in response.json()
    assert "customer_id" not in response.json()


def test_openapi_contains_only_lifecycle_routes(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'openapi.sqlite3').as_posix()}")
    with TestClient(app) as client:
        openapi_response = client.get("/openapi.json")

    assert openapi_response.status_code == 200
    paths = openapi_response.json()["paths"]
    assert set(paths) == {
        "/api/sessions",
        "/api/sessions/{session_id}",
        "/api/sessions/{session_id}/messages",
        "/api/sessions/{session_id}/end",
    }


def test_separate_client_connection_reads_persisted_session(tmp_path: Path) -> None:
    database_path = tmp_path / "reopen.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    session_id: UUID
    with TestClient(create_app(database_url)) as client:
        response = client.post("/api/sessions", json={})
        session_id = UUID(response.json()["session"]["session_id"])

    with TestClient(create_app(database_url)) as reopened_client:
        response = reopened_client.get(f"/api/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["session_id"] == str(session_id)
