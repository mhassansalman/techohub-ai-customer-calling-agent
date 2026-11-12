from datetime import UTC, datetime, timedelta
from pathlib import Path
import re
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, select

from backend.fixtures import load_demo_salon_fixture
from backend.main import create_app
from backend.models import (
    AuditEvent,
    ConversationSession,
    HandoffTicket,
    Message,
    MessageRole,
)
from backend.session_service import ASSISTANT_DISCLOSURE, start_session


def _message_payload(session_id: str) -> dict[str, object]:
    return {
        "session_id": session_id,
        "trace_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "channel_type": "text_web",
        "modality": "text",
        "message_text": "TEST ONLY: What are your hours?",
    }

# Per-session access tokens issued at session start. Session-scoped endpoints
# now require the X-Session-Token header, so tests capture the token returned
# by session creation and forward it on every subsequent request.
_session_tokens: dict[str, str] = {}


def _start_session(client: TestClient) -> str:
    started = client.post("/api/sessions", json={"channel_type": "text_web"})
    assert started.status_code == 201
    body = started.json()
    session_id = body["session"]["session_id"]
    _session_tokens[session_id] = body["access_token"]
    return session_id


def _token_headers(session_id: str) -> dict[str, str]:
    token = _session_tokens.get(session_id)
    return {"X-Session-Token": token} if token else {}


def _seed_tickets(app, count: int) -> list[tuple[str, datetime]]:
    with app.state.session_factory() as db:
        conversation = start_session(db, channel_type="text_web")
        session_id = conversation.id
        base_time = datetime(2026, 1, 1, tzinfo=UTC)
        messages = []
        tickets = []
        for index in range(count):
            message_id = str(uuid4())
            messages.append(
                Message(
                    id=message_id,
                    session_id=session_id,
                    sequence=index + 2,
                    role=MessageRole.CUSTOMER.value,
                    text=f"TEST ONLY: originating request {index}",
                    timestamp=base_time + timedelta(seconds=index // 2),
                    modality="text",
                )
            )
            tickets.append(
                HandoffTicket(
                    id=str(uuid4()),
                    session_id=session_id,
                    originating_message_id=message_id,
                    status="queued",
                    created_at=base_time + timedelta(seconds=index // 2),
                )
            )
        db.add_all(messages)
        db.flush()
        db.add_all(tickets)
        db.commit()
    return [(ticket.id, ticket.created_at) for ticket in tickets]


def test_api_start_message_status_and_end_lifecycle(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'api.sqlite3').as_posix()}")
    with TestClient(app) as client:
        started = client.post("/api/sessions", json={"channel_type": "text_web"})
        assert started.status_code == 201
        start_payload = started.json()
        session_id = start_payload["session"]["session_id"]
        _session_tokens[session_id] = start_payload["access_token"]

        assert start_payload["session"]["status"] == "active"
        assert start_payload["session"]["message_count"] == 1
        assert start_payload["assistant_disclosure"] == ASSISTANT_DISCLOSURE

        sent = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=_message_payload(session_id),
        )
        assert sent.status_code == 200
        message_payload = sent.json()
        assert message_payload["customer_message"]["text"] == (
            "TEST ONLY: What are your hours?"
        )
        assert "Monday" in message_payload["assistant_message"]["text"]
        assert "Etc/UTC" in message_payload["assistant_message"]["text"]

        status_response = client.get(
            f"/api/sessions/{session_id}", headers=_token_headers(session_id)
        )
        assert status_response.status_code == 200
        assert status_response.json()["message_count"] == 3
        assert status_response.json()["audit_event_count"] == 3
        assert "messages" not in status_response.json()

        ended = client.post(
            f"/api/sessions/{session_id}/end",
            headers=_token_headers(session_id),
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
            "assistant.response_delivered",
            "session.ended",
        }


def test_service_catalog_api_returns_only_approved_active_service_fields(
    tmp_path: Path,
) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'service_catalog.sqlite3').as_posix()}")
    expected = [
        {
            "service_id": service.service_id,
            "name": service.name,
            "price_amount": str(service.price_amount),
            "currency": service.currency,
            "duration_minutes": service.duration_minutes,
        }
        for service in load_demo_salon_fixture().services
        if service.active
    ]

    with TestClient(app) as client:
        response = client.get("/api/services")

    assert response.status_code == 200
    assert response.json() == expected
    assert all(
        set(service) == {
            "service_id",
            "name",
            "price_amount",
            "currency",
            "duration_minutes",
        }
        for service in response.json()
    )
    assert not any(
        "slot" in field or "appointment" in field
        for service in response.json()
        for field in service
    )


@pytest.mark.parametrize(
    "catalog_error",
    [FileNotFoundError("missing catalog"), ValueError("invalid catalog")],
)
def test_service_catalog_api_fails_safely_when_approved_catalog_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    catalog_error: Exception,
) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'invalid_service_catalog.sqlite3').as_posix()}")

    def fail_catalog_load():
        raise catalog_error

    monkeypatch.setattr("backend.main.load_demo_salon_fixture", fail_catalog_load)
    with TestClient(app) as client:
        response = client.get("/api/services")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Approved service catalog is temporarily unavailable."
    }


def test_service_card_inquiry_uses_existing_message_flow_without_ticket_mutations(
    tmp_path: Path,
) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'service_inquiry.sqlite3').as_posix()}")
    with TestClient(app) as client:
        session_id = _start_session(client)
        payload = _message_payload(session_id)
        payload["message_text"] = "What is the price and duration of Haircut?"

        response = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=payload,
        )
        status_response = client.get(
            f"/api/sessions/{session_id}", headers=_token_headers(session_id)
        )
        with app.state.session_factory() as db:
            tickets = list(db.scalars(select(HandoffTicket)))

    assert response.status_code == 200
    assert response.json()["customer_message"]["session_id"] == session_id
    assert "A haircut costs $35 and takes about 30 minutes." in response.json()[
        "assistant_message"
    ]["text"]
    assert "ticket ID" not in response.json()["assistant_message"]["text"]
    assert status_response.json()["message_count"] == 3
    assert tickets == []


def test_api_persists_browser_voice_transcript_channel_and_cancelled_outcome(
    tmp_path: Path,
) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'browser_voice.sqlite3').as_posix()}")
    with TestClient(app) as client:
        started = client.post(
            "/api/sessions",
            json={"channel_type": "browser_voice"},
        )
        assert started.status_code == 201
        start_payload = started.json()
        session_id = start_payload["session"]["session_id"]
        _session_tokens[session_id] = start_payload["access_token"]
        assert start_payload["session"]["channel_type"] == "browser_voice"
        assert "recognized speech transcripts are stored" in start_payload[
            "assistant_disclosure"
        ]
        assert "Microphone audio is not stored" in start_payload["assistant_disclosure"]

        payload = _message_payload(session_id)
        payload.update(
            {
                "channel_type": "browser_voice",
                "modality": "speech_transcript",
                "language": "en-US",
                "asr_confidence": 0.91,
            }
        )
        sent = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=payload,
        )
        assert sent.status_code == 200
        result = sent.json()
        assert result["customer_message"]["modality"] == "speech_transcript"
        assert result["customer_message"]["language"] == "en-US"
        assert result["customer_message"]["asr_confidence"] == 0.91
        assert result["assistant_message"]["text"]

        ended = client.post(
            f"/api/sessions/{session_id}/end",
            headers=_token_headers(session_id),
            json={"outcome": "cancelled"},
        )
        assert ended.status_code == 200
        assert ended.json()["outcome"] == "cancelled"

        with app.state.session_factory() as db:
            session = db.get(ConversationSession, session_id)
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

    assert session is not None
    assert session.channel == "browser_voice"
    assert session.outcome == "cancelled"
    assert messages[1].text == payload["message_text"]
    assert messages[1].modality == "speech_transcript"
    assert messages[1].language == "en-US"
    assert messages[1].asr_confidence == 0.91
    assert messages[2].text == result["assistant_message"]["text"]
    assert all(event.session_id == session_id for event in audits)
    assert any(
        event.action == "message.received"
        and event.resource_id == messages[1].id
        for event in audits
    )
    assert any(
        event.action == "session.ended" and event.outcome == "cancelled"
        for event in audits
    )


def test_mock_call_api_lifecycle_persists_transcript_and_cancelled_outcome(
    tmp_path: Path,
) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'mock_call.sqlite3').as_posix()}")
    with TestClient(app) as client:
        started = client.post(
            "/api/sessions",
            json={"channel_type": "mock_call"},
        )
        assert started.status_code == 201
        start_payload = started.json()
        session_id = start_payload["session"]["session_id"]
        _session_tokens[session_id] = start_payload["access_token"]

        payload = _message_payload(session_id)
        payload.update(
            {
                "channel_type": "mock_call",
                "message_text": "How much is a haircut?",
            }
        )
        sent = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=payload,
        )
        assert sent.status_code == 200
        result = sent.json()
        assert "$35" in result["assistant_message"]["text"]

        ended = client.post(
            f"/api/sessions/{session_id}/end",
            headers=_token_headers(session_id),
            json={"outcome": "cancelled"},
        )
        assert ended.status_code == 200
        assert ended.json()["outcome"] == "cancelled"

        with app.state.session_factory() as db:
            session = db.get(ConversationSession, session_id)
            messages = list(
                db.scalars(
                    select(Message)
                    .where(Message.session_id == session_id)
                    .order_by(Message.sequence)
                )
            )
            audits = list(
                db.scalars(
                    select(AuditEvent).where(AuditEvent.session_id == session_id)
                )
            )

    assert session is not None
    assert session.channel == "mock_call"
    assert session.outcome == "cancelled"
    assert messages[1].text == "How much is a haircut?"
    assert messages[1].modality == "text"
    assert messages[1].language is None
    assert messages[1].asr_confidence is None
    assert messages[2].text == result["assistant_message"]["text"]
    assert any(
        audit.action == "message.received" and audit.resource_id == messages[1].id
        for audit in audits
    )
    assert any(
        audit.action == "session.ended" and audit.outcome == "cancelled"
        for audit in audits
    )


@pytest.mark.parametrize(
    ("channel_type", "modality"),
    [
        ("text_web", "text"),
        ("browser_voice", "speech_transcript"),
        ("browser_voice", "text"),
    ],
)
def test_api_creates_confirmed_ticket_and_returns_persisted_id_once(
    tmp_path: Path,
    channel_type: str,
    modality: str,
) -> None:
    database_path = tmp_path / f"handoff_{channel_type}_{modality}.sqlite3"
    app = create_app(f"sqlite:///{database_path.as_posix()}")
    with TestClient(app) as client:
        started = client.post(
            "/api/sessions",
            json={"channel_type": channel_type},
        )
        session_id = started.json()["session"]["session_id"]
        _session_tokens[session_id] = started.json()["access_token"]

        request_payload = _message_payload(session_id)
        request_payload.update(
            {
                "channel_type": channel_type,
                "modality": modality,
                "message_text": "I want to speak to someone.",
            }
        )
        handoff_request = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=request_payload,
        )
        assert handoff_request.status_code == 200
        assert "reply yes or no" in handoff_request.json()[
            "assistant_message"
        ]["text"]

        ambiguous_payload = _message_payload(session_id)
        ambiguous_payload.update(
            {
                "channel_type": channel_type,
                "modality": modality,
                "message_text": "maybe",
            }
        )
        ambiguous = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=ambiguous_payload,
        )
        assert "yes or no" in ambiguous.json()["assistant_message"]["text"]
        with app.state.session_factory() as db:
            assert db.scalar(select(HandoffTicket)) is None

        confirmation_payload = _message_payload(session_id)
        confirmation_payload.update(
            {
                "channel_type": channel_type,
                "modality": modality,
                "message_text": "Yes, please.",
            }
        )
        confirmed = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=confirmation_payload,
        )
        assert confirmed.status_code == 200
        response_text = confirmed.json()["assistant_message"]["text"]
        ticket_id_match = re.search(
            r"ticket ID is ([0-9a-f-]{36})", response_text
        )
        assert ticket_id_match is not None
        ticket_id = ticket_id_match.group(1)

        repeated_confirmation = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=confirmation_payload,
        )
        assert repeated_confirmation.status_code == 200

        with app.state.session_factory() as db:
            ticket = db.get(HandoffTicket, ticket_id)
            tickets = list(db.scalars(select(HandoffTicket)))
            ticket_audit = db.scalar(
                select(AuditEvent).where(
                    AuditEvent.action == "handoff_ticket.queued",
                    AuditEvent.resource_id == ticket_id,
                )
            )

    assert ticket is not None
    assert ticket.status == "queued"
    assert ticket.session_id == session_id
    assert ticket.originating_message_id == handoff_request.json()[
        "customer_message"
    ]["message_id"]
    assert len(tickets) == 1
    assert ticket_audit is not None
    assert ticket_audit.session_id == session_id
    assert ticket_audit.resource_type == "handoff_ticket"


def test_api_ticket_persistence_failure_never_claims_success(
    tmp_path: Path,
) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'handoff_failure.sqlite3').as_posix()}")

    def fail_ticket_insert(
        connection, cursor, statement, parameters, context, executemany
    ) -> None:
        if statement.lstrip().startswith("INSERT INTO handoff_tickets"):
            raise RuntimeError("simulated ticket persistence failure")

    event.listen(app.state.database_engine, "before_cursor_execute", fail_ticket_insert)
    try:
        with TestClient(app) as client:
            started = client.post("/api/sessions", json={"channel_type": "text_web"})
            session_id = started.json()["session"]["session_id"]
            _session_tokens[session_id] = started.json()["access_token"]
            request_payload = _message_payload(session_id)
            request_payload["message_text"] = "I want to speak to someone."
            client.post(
                f"/api/sessions/{session_id}/messages",
                headers=_token_headers(session_id),
                json=request_payload,
            )

            confirmation_payload = _message_payload(session_id)
            confirmation_payload["message_text"] = "Yes"
            failed = client.post(
                f"/api/sessions/{session_id}/messages",
                headers=_token_headers(session_id),
                json=confirmation_payload,
            )
            response_text = failed.json()["assistant_message"]["text"]

            with app.state.session_factory() as db:
                tickets = list(db.scalars(select(HandoffTicket)))
    finally:
        event.remove(
            app.state.database_engine,
            "before_cursor_execute",
            fail_ticket_insert,
        )

    assert failed.status_code == 200
    assert "couldn't safely complete" in response_text
    assert "ticket ID" not in response_text
    assert tickets == []


def test_confirmed_ticket_is_retrievable_through_staff_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staff_api_key = "test-only-staff-api-key"
    monkeypatch.setenv("STAFF_API_KEY", staff_api_key)
    app = create_app(f"sqlite:///{(tmp_path / 'ticket_staff_read.sqlite3').as_posix()}")
    with TestClient(app) as client:
        started = client.post("/api/sessions", json={"channel_type": "text_web"})
        assert started.status_code == 201
        session_id = started.json()["session"]["session_id"]
        _session_tokens[session_id] = started.json()["access_token"]

        request_payload = _message_payload(session_id)
        request_payload["message_text"] = "I want to speak to someone."
        handoff_request = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=request_payload,
        )
        assert handoff_request.status_code == 200
        assert "reply yes or no" in handoff_request.json()[
            "assistant_message"
        ]["text"]

        confirmation_payload = _message_payload(session_id)
        confirmation_payload["message_text"] = "Yes, please."
        confirmed = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=confirmation_payload,
        )
        assert confirmed.status_code == 200
        ticket_id_match = re.search(
            r"ticket ID is ([0-9a-f-]{36})",
            confirmed.json()["assistant_message"]["text"],
        )
        assert ticket_id_match is not None
        ticket_id = ticket_id_match.group(1)

        retrieved = client.get(
            f"/api/staff/tickets/{ticket_id}",
            headers={"X-Staff-API-Key": staff_api_key},
        )
        unauthenticated = client.get(f"/api/staff/tickets/{ticket_id}")
        with app.state.session_factory() as db:
            ticket = db.get(HandoffTicket, ticket_id)

    assert retrieved.status_code == 200
    ticket_data = retrieved.json()
    assert ticket_data["id"] == ticket_id
    assert ticket_data["session_id"] == session_id
    assert ticket_data["originating_message_id"] == handoff_request.json()[
        "customer_message"
    ]["message_id"]
    assert ticket_data["status"] == "queued"
    assert set(ticket_data) == {
        "id",
        "session_id",
        "originating_message_id",
        "status",
        "created_at",
    }
    assert "I want to speak to someone." not in str(ticket_data)
    assert unauthenticated.status_code == 401
    assert ticket is not None
    assert ticket.id == ticket_id
    assert ticket.session_id == session_id
    assert ticket.status == "queued"


def test_staff_ticket_endpoints_fail_closed_when_server_secret_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'staff_unconfigured.sqlite3').as_posix()}")
    with TestClient(app) as client:
        for configured_key in (None, ""):
            if configured_key is None:
                monkeypatch.delenv("STAFF_API_KEY", raising=False)
            else:
                monkeypatch.setenv("STAFF_API_KEY", configured_key)
            response = client.get(
                "/api/staff/tickets",
                headers={"X-Staff-API-Key": "any-request-key"},
            )
            assert response.status_code == 503
            assert "not configured" in response.json()["detail"]


def test_staff_ticket_endpoints_reject_missing_and_invalid_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'staff_unauthorized.sqlite3').as_posix()}")
    monkeypatch.setenv("STAFF_API_KEY", "staff-test-secret")
    with TestClient(app) as client:
        assert client.get("/api/staff/tickets").status_code == 401
        assert client.get(
            "/api/staff/tickets",
            headers={"X-Staff-API-Key": ""},
        ).status_code == 401
        assert client.get(
            "/api/staff/tickets",
            headers={"X-Staff-API-Key": "incorrect"},
        ).status_code == 401
        unknown_id = str(uuid4())
        assert client.get(
            f"/api/staff/tickets/{unknown_id}",
        ).status_code == 401
        assert client.get(
            f"/api/staff/tickets/{unknown_id}",
            headers={"X-Staff-API-Key": "incorrect"},
        ).status_code == 401


def test_staff_ticket_listing_is_ordered_limited_and_minimal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'staff_list.sqlite3').as_posix()}")
    monkeypatch.setenv("STAFF_API_KEY", "staff-test-secret")
    headers = {"X-Staff-API-Key": "staff-test-secret"}

    with TestClient(app) as client:
        ticket_ids = _seed_tickets(app, 105)
        default_response = client.get("/api/staff/tickets", headers=headers)
        assert default_response.status_code == 200
        default_tickets = default_response.json()
        maximum_response = client.get(
            "/api/staff/tickets?limit=100",
            headers=headers,
        )
        assert maximum_response.status_code == 200
        maximum_tickets = maximum_response.json()
        assert client.get(
            "/api/staff/tickets?limit=0",
            headers=headers,
        ).status_code == 422
        assert client.get(
            "/api/staff/tickets?limit=101",
            headers=headers,
        ).status_code == 422
        assert client.get(
            "/api/staff/tickets?limit=not-a-number",
            headers=headers,
        ).status_code == 422

    assert len(default_tickets) == 50
    assert len(maximum_tickets) == 100
    expected_order = [
        ticket_id
        for ticket_id, _ in sorted(
            ticket_ids,
            key=lambda ticket: (ticket[1], ticket[0]),
            reverse=True,
        )
    ][:100]
    assert [ticket["id"] for ticket in maximum_tickets] == expected_order
    assert all(ticket["status"] == "queued" for ticket in maximum_tickets)
    assert set(maximum_tickets[0]) == {
        "id",
        "session_id",
        "originating_message_id",
        "status",
        "created_at",
    }
    assert "TEST ONLY:" not in str(maximum_tickets)


def test_staff_ticket_detail_requires_auth_and_returns_safe_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'staff_detail.sqlite3').as_posix()}")
    monkeypatch.setenv("STAFF_API_KEY", "staff-test-secret")
    headers = {"X-Staff-API-Key": "staff-test-secret"}

    with TestClient(app) as client:
        ticket_id = _seed_tickets(app, 1)[0][0]
        response = client.get(f"/api/staff/tickets/{ticket_id}", headers=headers)
        assert response.status_code == 200
        assert client.get(
            f"/api/staff/tickets/{uuid4()}",
            headers=headers,
        ).status_code == 404
        assert client.get(
            "/api/staff/tickets/not-a-uuid",
            headers=headers,
        ).status_code == 422
        unauthenticated_unknown = client.get(
            f"/api/staff/tickets/{uuid4()}",
        )
        assert unauthenticated_unknown.status_code == 401
        public_session = client.post(
            "/api/sessions",
            json={"channel_type": "text_web"},
        )
        assert public_session.status_code == 201
        public_session_id = public_session.json()["session"]["session_id"]
        _session_tokens[public_session_id] = public_session.json()["access_token"]
        public_message = client.post(
            f"/api/sessions/{public_session_id}/messages",
            headers=_token_headers(public_session_id),
            json=_message_payload(public_session_id),
        )

    assert public_message.status_code == 200
    assert set(response.json()) == {
        "id",
        "session_id",
        "originating_message_id",
        "status",
        "created_at",
    }
    assert response.json()["id"] == ticket_id
    assert "TEST ONLY:" not in str(response.json())
    assert "staff-test-secret" not in str(response.json())


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

        session_id = _start_session(client)
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
        session_id = _start_session(client)

        mismatch = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=_message_payload(str(uuid4())),
        )
        assert mismatch.status_code == 422

        wrong_channel = _message_payload(session_id)
        wrong_channel["channel_type"] = "browser_voice"
        response = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=wrong_channel,
        )
        assert response.status_code == 422


def test_api_rejects_message_after_close_and_duplicate_end(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'closed.sqlite3').as_posix()}")
    with TestClient(app) as client:
        session_id = _start_session(client)

        ended = client.post(
            f"/api/sessions/{session_id}/end",
            headers=_token_headers(session_id),
            json={"outcome": "cancelled"},
        )
        assert ended.status_code == 200

        message_result = client.post(
            f"/api/sessions/{session_id}/messages",
            headers=_token_headers(session_id),
            json=_message_payload(session_id),
        )
        assert message_result.status_code == 409

        duplicate_end = client.post(
            f"/api/sessions/{session_id}/end",
            headers=_token_headers(session_id),
            json={"outcome": "cancelled"},
        )
        assert duplicate_end.status_code == 409


def test_status_endpoint_does_not_expose_transcript(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'status.sqlite3').as_posix()}")
    with TestClient(app) as client:
        session_id = _start_session(client)
        response = client.get(
            f"/api/sessions/{session_id}", headers=_token_headers(session_id)
        )

    assert response.status_code == 200
    assert "messages" not in response.json()
    assert "customer_id" not in response.json()


def test_openapi_contains_lifecycle_and_read_only_staff_routes(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'openapi.sqlite3').as_posix()}")
    with TestClient(app) as client:
        openapi_response = client.get("/openapi.json")

    assert openapi_response.status_code == 200
    paths = openapi_response.json()["paths"]
    assert set(paths) == {
        "/api/services",
        "/api/sessions",
        "/api/sessions/{session_id}",
        "/api/sessions/{session_id}/messages",
        "/api/sessions/{session_id}/end",
        "/api/staff/tickets",
        "/api/staff/tickets/{ticket_id}",
    }


def test_separate_client_connection_reads_persisted_session(tmp_path: Path) -> None:
    database_path = tmp_path / "reopen.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    session_id: UUID
    with TestClient(create_app(database_url)) as client:
        session_id = _start_session(client)

    with TestClient(create_app(database_url)) as reopened_client:
        response = reopened_client.get(
            f"/api/sessions/{session_id}", headers=_token_headers(session_id)
        )

    assert response.status_code == 200
    assert response.json()["session_id"] == str(session_id)

def test_concurrent_sessions_have_strict_data_and_handoff_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STAFF_API_KEY", "test-staff-key-isolation")
    database_path = tmp_path / "isolation.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    app = create_app(database_url)

    with TestClient(app) as client:
        res_a = client.post("/api/sessions", json={"channel_type": "text_web"})
        assert res_a.status_code == 201
        session_a = res_a.json()["session"]["session_id"]
        _session_tokens[session_a] = res_a.json()["access_token"]

        res_b = client.post("/api/sessions", json={"channel_type": "text_web"})
        assert res_b.status_code == 201
        session_b = res_b.json()["session"]["session_id"]
        _session_tokens[session_b] = res_b.json()["access_token"]
        assert session_a != session_b

        payload_a1 = {
            "session_id": session_a,
            "trace_id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "channel_type": "text_web",
            "modality": "text",
            "message_text": "I want to speak with a human.",
        }
        res_a1 = client.post(
            f"/api/sessions/{session_a}/messages",
            headers=_token_headers(session_a),
            json=payload_a1,
        )
        assert res_a1.status_code == 200
        assert (
            "Would you like me to create a queued support ticket"
            in res_a1.json()["assistant_message"]["text"]
        )

        payload_b1 = {
            "session_id": session_b,
            "trace_id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "channel_type": "text_web",
            "modality": "text",
            "message_text": "yes",
        }
        res_b1 = client.post(
            f"/api/sessions/{session_b}/messages",
            headers=_token_headers(session_b),
            json=payload_b1,
        )
        assert res_b1.status_code == 200
        assert (
            res_b1.json()["assistant_message"]["text"]
            == "Thanks. What can I help you with?"
        )

        payload_a2 = {
            "session_id": session_a,
            "trace_id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "channel_type": "text_web",
            "modality": "text",
            "message_text": "yes",
        }
        res_a2 = client.post(
            f"/api/sessions/{session_a}/messages",
            headers=_token_headers(session_a),
            json=payload_a2,
        )
        assert res_a2.status_code == 200
        assert (
            "Your support ticket has been queued. Your ticket ID is"
            in res_a2.json()["assistant_message"]["text"]
        )

        tickets_res = client.get(
            "/api/staff/tickets",
            headers={"X-Staff-API-Key": "test-staff-key-isolation"},
        )
        assert tickets_res.status_code == 200
        tickets = tickets_res.json()
        assert len(tickets) == 1
        assert tickets[0]["session_id"] == session_a
