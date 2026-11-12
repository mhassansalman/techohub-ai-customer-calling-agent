from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.channels import ChannelType, CustomerRequest, InputModality
from backend.main import create_app
from backend.workflow import _handoff_confirmation_decision  # noqa: F401


class RulesOnlyClassifier:
    async def classify(
        self,
        text: str,
        *,
        has_pending_availability_context: bool = False,
    ):
        from backend.intent import classify_with_rules

        return classify_with_rules(
            text, has_pending_availability_context=has_pending_availability_context
        )


def _create_app(tmp_path):
    return create_app(
        f"sqlite:///{(tmp_path / 'security.sqlite3').as_posix()}",
        classifier=RulesOnlyClassifier(),
    )


def _start_session(client):
    response = client.post("/api/sessions", json={"channel_type": "text_web"})
    assert response.status_code == 201
    body = response.json()
    session_id = UUID(body["session"]["session_id"])
    assert body["access_token"]
    assert body["access_token"] != str(session_id)
    return session_id, body["access_token"]


def _message_payload(session_id, text="security probe"):
    return {
        "session_id": str(session_id),
        "trace_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "channel_type": "text_web",
        "modality": "text",
        "message_text": text,
    }


def test_session_creation_issues_unpredictable_access_token(tmp_path):
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id, token = _start_session(client)
    assert isinstance(token, str) and len(token) >= 22
    assert token != str(session_id)
    # Token must be issued separately from the public session identifier.
    assert ":" not in token


def test_session_status_requires_access_token(tmp_path):
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id, token = _start_session(client)

        # No token -> 401.
        assert client.get(f"/api/sessions/{session_id}").status_code == 401

        # Wrong token -> 401.
        assert (
            client.get(
                f"/api/sessions/{session_id}",
                headers={"X-Session-Token": "wrong-token"},
            ).status_code
            == 401
        )

        # Valid token -> 200 and no transcript exposure.
        response = client.get(
            f"/api/sessions/{session_id}", headers={"X-Session-Token": token}
        )
        assert response.status_code == 200
        assert "messages" not in response.json()
        assert "customer_id" not in response.json()


def test_message_submission_requires_access_token(tmp_path):
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id, token = _start_session(client)
        payload = _message_payload(session_id)

        # No token -> 401.
        assert (
            client.post(f"/api/sessions/{session_id}/messages", json=payload).status_code
            == 401
        )

        # Wrong token -> 401.
        assert (
            client.post(
                f"/api/sessions/{session_id}/messages",
                json=payload,
                headers={"X-Session-Token": "wrong-token"},
            ).status_code
            == 401
        )

        # Valid token -> 200.
        response = client.post(
            f"/api/sessions/{session_id}/messages",
            json=payload,
            headers={"X-Session-Token": token},
        )
        assert response.status_code == 200


def test_session_termination_requires_access_token(tmp_path):
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id, token = _start_session(client)

        # No token -> 401.
        assert (
            client.post(f"/api/sessions/{session_id}/end", json={"outcome": "cancelled"}).status_code
            == 401
        )

        # Wrong token -> 401.
        assert (
            client.post(
                f"/api/sessions/{session_id}/end",
                json={"outcome": "cancelled"},
                headers={"X-Session-Token": "wrong-token"},
            ).status_code
            == 401
        )

        # Valid token -> 200.
        response = client.post(
            f"/api/sessions/{session_id}/end",
            json={"outcome": "cancelled"},
            headers={"X-Session-Token": token},
        )
        assert response.status_code == 200


def test_cross_session_isolation_via_access_token(tmp_path):
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_a, token_a = _start_session(client)
        session_b, token_b = _start_session(client)
        payload_a = _message_payload(session_a, "message from A")

        # Token for session A cannot read session B status.
        assert (
            client.get(
                f"/api/sessions/{session_b}", headers={"X-Session-Token": token_a}
            ).status_code
            == 401
        )

        # Token for session A cannot submit to session B.
        payload_b = _message_payload(session_b, "message from B")
        assert (
            client.post(
                f"/api/sessions/{session_b}/messages",
                json=payload_b,
                headers={"X-Session-Token": token_a},
            ).status_code
            == 401
        )

        # Token for session A cannot terminate session B.
        assert (
            client.post(
                f"/api/sessions/{session_b}/end",
                json={"outcome": "cancelled"},
                headers={"X-Session-Token": token_a},
            ).status_code
            == 401
        )

        # Each token operates only on its own session.
        assert client.post(
            f"/api/sessions/{session_a}/messages",
            json=payload_a,
            headers={"X-Session-Token": token_a},
        ).status_code == 200
        assert client.post(
            f"/api/sessions/{session_b}/messages",
            json=_message_payload(session_b, "message from B"),
            headers={"X-Session-Token": token_b},
        ).status_code == 200


def test_session_token_not_leaked_into_url_or_response_body(tmp_path):
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id, token = _start_session(client)
        # Status response exposes only metadata, never the access token.
        response = client.get(
            f"/api/sessions/{session_id}", headers={"X-Session-Token": token}
        )
        body = response.text
        assert token not in body
        assert str(session_id) in body


def test_health_endpoint_requires_no_session_token(tmp_path):
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_cors_allows_only_configured_frontend_origin(tmp_path, monkeypatch):
    allowed_origin = "https://techohub-ai-customer-calling-agent.vercel.app"
    monkeypatch.setenv("TECHOHUB_CORS_ORIGINS", allowed_origin)
    app = _create_app(tmp_path)

    with TestClient(app) as client:
        allowed = client.options(
            "/api/sessions",
            headers={
                "Origin": allowed_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-session-token",
            },
        )
        denied = client.options(
            "/api/sessions",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-session-token",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == allowed_origin
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers
