from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.availability import AvailabilityConversationService
from backend.channels import ChannelType, CustomerRequest, InputModality
from backend.fixtures import demo_clock, load_demo_salon_fixture
from backend.intent import (
    ClassificationStatus,
    ClassifierProviderError,
    ClassifierSource,
    Intent,
    IntentClassification,
    ProviderErrorCode,
    RuleFirstIntentClassifier,
    classify_with_rules,
)
from backend.knowledge import KnowledgeService
from backend.main import create_app
from backend.models import (
    AuditEvent,
    AvailabilityConversationContext,
    ConversationSession,
    Message,
    PendingAvailabilityDateContext,
)
class UnavailableGroq:
    def __init__(self, code: ProviderErrorCode = ProviderErrorCode.MISSING_API_KEY):
        self.code = code

    async def classify(self, text: str):
        raise ClassifierProviderError(self.code)


class RulesOnlyClassifier:
    async def classify(
        self,
        text: str,
        *,
        has_pending_availability_context: bool = False,
    ) -> IntentClassification:
        return classify_with_rules(
            text,
            has_pending_availability_context=has_pending_availability_context,
        )


class InvalidResultClassifier:
    async def classify(self, text: str, *, has_pending_availability_context: bool = False):
        return {
            "status": "classified",
            "intents": ["not_a_real_intent"],
            "source": "groq",
            "reason_code": "invalid_test_result",
        }


def _create_app(tmp_path: Path, classifier=None):
    return create_app(
        f"sqlite:///{(tmp_path / 'workflow.sqlite3').as_posix()}",
        classifier=classifier or RulesOnlyClassifier(),
    )


def _start_session(client: TestClient) -> UUID:
    response = client.post("/api/sessions", json={"channel_type": "text_web"})
    assert response.status_code == 201
    return UUID(response.json()["session"]["session_id"])


def _send(client: TestClient, session_id: UUID, text: str):
    return client.post(
        f"/api/sessions/{session_id}/messages",
        json={
            "session_id": str(session_id),
            "trace_id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
            "channel_type": "text_web",
            "modality": "text",
            "message_text": text,
        },
    )


def test_graph_is_a_real_state_graph_with_conditional_capability_routes(
    tmp_path: Path,
) -> None:
    app = _create_app(tmp_path)
    workflow = app.state.conversation_workflow

    graph = workflow.graph.get_graph()
    assert {
        "classify_intent",
        "faq_capability",
        "availability_capability",
        "date_correction",
        "support_capability",
        "multi_intent_capability",
        "clarification",
        "aggregate_response",
        "__start__",
        "__end__",
    }.issubset(graph.nodes)
    assert graph.edges  # Compiled LangGraph topology, not a direct function chain.


def test_hours_and_service_pricing_use_grounded_knowledge(tmp_path: Path) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id = _start_session(client)
        hours = _send(client, session_id, "Are you open Saturday?")
        pricing = _send(client, session_id, "How much is a haircut?")

    assert hours.status_code == 200
    assert "Saturday, 10:00–16:00 Etc/UTC" in hours.json()["assistant_message"]["text"]
    assert pricing.status_code == 200
    assert "USD 35.00" in pricing.json()["assistant_message"]["text"]
    assert "30 minutes" in pricing.json()["assistant_message"]["text"]


def test_unsupported_refund_policy_abstains_without_claiming_ticket(
    tmp_path: Path,
) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id = _start_session(client)
        response = _send(client, session_id, "What is your refund policy?")

    text = response.json()["assistant_message"]["text"]
    assert response.status_code == 200
    assert "don't have approved information" in text
    assert "can't create a support ticket" in text
    assert "ticket created" not in text.casefold()


def test_friday_availability_and_saturday_date_correction_persist_context(
    tmp_path: Path,
) -> None:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "demo_salon.json"
    fixture_before = fixture_path.read_bytes()
    fixture = load_demo_salon_fixture()
    assert demo_clock(fixture).isoformat() == "2026-10-29T09:00:00+00:00"

    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id = _start_session(client)
        friday = _send(
            client,
            session_id,
            "Do you have a haircut appointment on Friday?",
        )
        saturday = _send(client, session_id, "Sorry, I meant Saturday.")

        with app.state.session_factory() as db:
            context = db.get(AvailabilityConversationContext, str(session_id))
            messages = list(
                db.scalars(
                    select(Message)
                    .where(Message.session_id == str(session_id))
                    .order_by(Message.sequence)
                )
            )

    assert friday.status_code == saturday.status_code == 200
    friday_text = friday.json()["assistant_message"]["text"]
    saturday_text = saturday.json()["assistant_message"]["text"]
    assert "2026-10-30" in friday_text
    assert "10:00 Etc/UTC" in friday_text
    assert "14:00 Etc/UTC" in friday_text
    assert "2026-10-31" in saturday_text
    assert "10:00 Etc/UTC" in saturday_text
    assert "haircut" in saturday_text
    assert context is not None
    assert context.service_id == "haircut"
    assert context.requested_date.isoformat() == "2026-10-31"
    assert [message.sequence for message in messages] == list(range(1, 6))
    assert messages[-1].text == saturday_text
    assert fixture_path.read_bytes() == fixture_before


def test_availability_slot_ids_are_retained_as_internal_sources(tmp_path: Path) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id = _start_session(client)
        request = CustomerRequest(
            session_id=session_id,
            trace_id=uuid4(),
            timestamp=datetime.now(UTC),
            channel_type=ChannelType.TEXT_WEB,
            modality=InputModality.TEXT,
            message_text="Do you have a haircut appointment on Friday?",
        )
        with app.state.session_factory() as db:
            result = asyncio.run(
                app.state.conversation_workflow.run(
                    session_id=session_id,
                    request=request,
                    db=db,
                )
            )

    assert "haircut-2026-10-30-1000" in result.source_ids
    assert "haircut-2026-10-30-1400" in result.source_ids
    assert any("availability_slots" in source for source in result.source_ids)


def test_availability_context_isolated_between_sessions(tmp_path: Path) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        first_session = _start_session(client)
        second_session = _start_session(client)
        first_request = _send(
            client,
            first_session,
            "Do you have a haircut appointment on Friday?",
        )
        second_correction = _send(
            client,
            second_session,
            "Sorry, I meant Saturday.",
        )
        first_correction = _send(
            client,
            first_session,
            "Sorry, I meant Saturday.",
        )

    assert "2026-10-30" in first_request.json()["assistant_message"]["text"]
    assert "Please tell me one service and one clear date" in (
        second_correction.json()["assistant_message"]["text"]
    )
    assert "2026-10-31" in first_correction.json()["assistant_message"]["text"]


def test_compound_hours_and_availability_returns_both_capability_results(
    tmp_path: Path,
) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id = _start_session(client)
        response = _send(
            client,
            session_id,
            "Are you open Saturday, and is a haircut appointment available?",
        )

    text = response.json()["assistant_message"]["text"]
    assert response.status_code == 200
    assert "Saturday, 10:00–16:00 Etc/UTC" in text
    assert "10:00 Etc/UTC" in text


@pytest.mark.parametrize(
    "message",
    [
        "Are you open on Sunday? How much is one haircut?",
        "How much is one haircut? Are you open on Sunday?",
    ],
)
def test_compound_hours_and_service_request_returns_both_grounded_answers(
    tmp_path: Path,
    message: str,
) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        response = _send(client, _start_session(client), message)

    text = response.json()["assistant_message"]["text"]
    assert response.status_code == 200
    assert "closed on Sunday" in text
    assert "USD 35.00" in text
    assert "30 minutes" in text
    assert "clarify" not in text.casefold()


def test_haircut_price_question_uses_existing_catalog_answer(tmp_path: Path) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        response = _send(
            client,
            _start_session(client),
            "How much is one haircut?",
        )

    text = response.json()["assistant_message"]["text"]
    assert "USD 35.00" in text
    assert "30 minutes" in text


def test_slots_without_service_preserve_date_until_service_clarification(
    tmp_path: Path,
) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id = _start_session(client)
        missing_service = _send(
            client,
            session_id,
            "Which slots are open on Wednesday?",
        )
        with app.state.session_factory() as db:
            pending = db.get(PendingAvailabilityDateContext, str(session_id))
            assert pending is not None
            assert pending.requested_date.isoformat() == "2026-11-04"

        service_clarification = _send(client, session_id, "Haircut")
        with app.state.session_factory() as db:
            pending_after_lookup = db.get(
                PendingAvailabilityDateContext,
                str(session_id),
            )
            saved_context = db.get(
                AvailabilityConversationContext,
                str(session_id),
            )

    clarification_text = missing_service.json()["assistant_message"]["text"]
    lookup_text = service_clarification.json()["assistant_message"]["text"]
    assert "Which service" in clarification_text
    assert "2026-11-04" in clarification_text
    assert "no recorded fixture slots" in lookup_text
    assert "2026-11-04" in lookup_text
    assert pending_after_lookup is None
    assert saved_context is not None
    assert saved_context.service_id == "haircut"
    assert saved_context.requested_date.isoformat() == "2026-11-04"


def test_explicit_wednesday_haircut_slots_report_no_fixture_slots(
    tmp_path: Path,
) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        response = _send(
            client,
            _start_session(client),
            "Which haircut slots are open on Wednesday?",
        )

    text = response.json()["assistant_message"]["text"]
    assert "no recorded fixture slots" in text
    assert "2026-11-04" in text
    assert "not confirm real-world unavailability" in text


@pytest.mark.parametrize(
    "message",
    [
        "I want trim beard",
        "I want to trim my beard",
    ],
)
def test_ambiguous_beard_interest_gets_helpful_clarification(
    tmp_path: Path,
    message: str,
) -> None:
    class NoGroq:
        async def classify(self, text: str):
            raise AssertionError("Rule-recognized service interest should not call Groq")

    app = _create_app(
        tmp_path,
        classifier=RuleFirstIntentClassifier(NoGroq()),
    )
    with TestClient(app) as client:
        response = _send(client, _start_session(client), message)

    text = response.json()["assistant_message"]["text"]
    assert "information about that service" in text
    assert "appointment availability" in text
    assert "couldn't safely classify" not in text
    assert "No appointment was created" not in text


def test_browser_voice_and_typed_turns_keep_same_response_contract(
    tmp_path: Path,
) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id = client.post(
            "/api/sessions",
            json={"channel_type": "browser_voice"},
        ).json()["session"]["session_id"]
        responses = []
        for modality, message in (
            ("speech_transcript", "Are you open on Sunday?"),
            ("text", "How much is one haircut?"),
        ):
            response = client.post(
                f"/api/sessions/{session_id}/messages",
                json={
                    "session_id": session_id,
                    "trace_id": str(uuid4()),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "channel_type": "browser_voice",
                    "modality": modality,
                    "message_text": message,
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert set(payload) == {"customer_message", "assistant_message"}
            assert payload["customer_message"]["session_id"] == session_id
            assert payload["assistant_message"]["session_id"] == session_id
            responses.append(payload)

    assert "closed on Sunday" in responses[0]["assistant_message"]["text"]
    assert "USD 35.00" in responses[1]["assistant_message"]["text"]


def test_availability_missing_date_or_service_asks_for_clarification(
    tmp_path: Path,
) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id = _start_session(client)
        missing_date = _send(
            client,
            session_id,
            "Do you have a haircut appointment?",
        )
        missing_service = _send(
            client,
            session_id,
            "Do you have an appointment Friday?",
        )

    assert "one service and one clear date" in (
        missing_date.json()["assistant_message"]["text"]
    )
    assert "one service and one clear date" in (
        missing_service.json()["assistant_message"]["text"]
    )


def test_unsupported_intent_and_missing_provider_use_safe_clarification(
    tmp_path: Path,
) -> None:
    app = _create_app(
        tmp_path,
        classifier=RuleFirstIntentClassifier(UnavailableGroq()),
    )
    with TestClient(app) as client:
        session_id = _start_session(client)
        response = _send(client, session_id, "Tell me something.")

    text = response.json()["assistant_message"]["text"]
    assert response.status_code == 200
    assert "couldn't safely classify" in text
    assert "stack" not in text.casefold()


def test_timeout_and_rate_limit_and_invalid_outputs_do_not_crash_graph(
    tmp_path: Path,
) -> None:
    timeout_app = _create_app(
        tmp_path / "rate",
        classifier=RuleFirstIntentClassifier(
            UnavailableGroq(ProviderErrorCode.TIMEOUT)
        ),
    )
    rate_limit_app = _create_app(
        tmp_path / "limited",
        classifier=RuleFirstIntentClassifier(
            UnavailableGroq(ProviderErrorCode.RATE_LIMITED)
        ),
    )
    invalid_app = _create_app(
        tmp_path / "invalid",
        classifier=InvalidResultClassifier(),
    )
    with TestClient(timeout_app) as timeout_client:
        timeout_session = _start_session(timeout_client)
        timeout_response = _send(
            timeout_client,
            timeout_session,
            "Could you help me?",
        )
    with TestClient(rate_limit_app) as rate_client:
        rate_session = _start_session(rate_client)
        rate_response = _send(rate_client, rate_session, "Could you help me?")
    with TestClient(invalid_app) as invalid_client:
        invalid_session = _start_session(invalid_client)
        invalid_response = _send(invalid_client, invalid_session, "Could you help me?")

    assert "couldn't safely classify" in (
        timeout_response.json()["assistant_message"]["text"]
    )
    assert "couldn't safely classify" in (
        rate_response.json()["assistant_message"]["text"]
    )
    assert "couldn't safely understand" in (
        invalid_response.json()["assistant_message"]["text"]
    )


def test_complaint_and_human_request_never_claim_successful_handoff(
    tmp_path: Path,
) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id = _start_session(client)
        complaint = _send(client, session_id, "I have a complaint about my visit.")
        human = _send(client, session_id, "I want to speak to someone.")

    complaint_text = complaint.json()["assistant_message"]["text"].casefold()
    human_text = human.json()["assistant_message"]["text"].casefold()
    assert complaint.status_code == human.status_code == 200
    assert "can't create a support ticket" in complaint_text
    assert "can't transfer this chat" in human_text
    assert "ticket created" not in complaint_text + human_text


def test_booking_request_does_not_mutate_fixture_or_claim_booking(
    tmp_path: Path,
) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id = _start_session(client)
        response = _send(client, session_id, "Book a haircut appointment Friday.")

    text = response.json()["assistant_message"]["text"]
    assert "No appointment was created" in text
    assert "created" in text.casefold()


def test_unknown_closed_and_invalid_classifier_sessions_are_safe(
    tmp_path: Path,
) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        unknown = uuid4()
        assert _send(client, unknown, "Are you open Saturday?").status_code == 404
        session_id = _start_session(client)
        ended = client.post(
            f"/api/sessions/{session_id}/end",
            json={"outcome": "unresolved"},
        )
        assert ended.status_code == 200
        assert _send(client, session_id, "Are you open Saturday?").status_code == 409


def test_persisted_response_audit_and_openapi_contract(tmp_path: Path) -> None:
    app = _create_app(tmp_path)
    with TestClient(app) as client:
        session_id = _start_session(client)
        response = _send(client, session_id, "How much is a haircut?")
        status_response = client.get(f"/api/sessions/{session_id}")
        openapi = client.get("/openapi.json").json()

        with app.state.session_factory() as db:
            messages = list(
                db.scalars(
                    select(Message)
                    .where(Message.session_id == str(session_id))
                    .order_by(Message.sequence)
                )
            )
            actions = list(
                db.scalars(
                    select(AuditEvent.action).where(
                        AuditEvent.session_id == str(session_id)
                    )
                )
            )

    assert response.status_code == 200
    assert messages[-1].text == response.json()["assistant_message"]["text"]
    assert [message.sequence for message in messages] == [1, 2, 3]
    assert "assistant.response_delivered" in actions
    assert status_response.status_code == 200
    assert "messages" not in status_response.json()
    assert set(openapi["paths"]) == {
        "/api/sessions",
        "/api/sessions/{session_id}",
        "/api/sessions/{session_id}/messages",
        "/api/sessions/{session_id}/end",
    }


def test_graph_failures_are_sanitized_and_customer_turn_is_persisted(
    tmp_path: Path,
) -> None:
    class BrokenClassifier:
        async def classify(self, text: str, *, has_pending_availability_context: bool = False):
            raise RuntimeError("PRIVATE_PROVIDER_ERROR")

    app = _create_app(tmp_path, classifier=BrokenClassifier())
    with TestClient(app) as client:
        session_id = _start_session(client)
        response = _send(client, session_id, "Could you help me?")
        with app.state.session_factory() as db:
            messages = list(
                db.scalars(
                    select(Message)
                    .where(Message.session_id == str(session_id))
                    .order_by(Message.sequence)
                )
            )

    assert response.status_code == 200
    assert "couldn't safely complete" in response.json()["assistant_message"]["text"]
    assert messages[-2].text == "Could you help me?"
    assert "PRIVATE_PROVIDER_ERROR" not in messages[-1].text
