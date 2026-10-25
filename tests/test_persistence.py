from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from backend.channels import ChannelType, CustomerRequest, InputModality
from backend.database import Base, create_database_engine, create_session_factory
from backend.fixtures import CANONICAL_FIXTURE_PATH
from backend.models import (
    AuditEvent,
    ConversationSession,
    Message,
    MessageRole,
    SessionOutcome,
    SessionStatus,
)
from backend.session_service import (
    SessionAlreadyClosedError,
    SessionClosedError,
    SessionNotFoundError,
    append_customer_message,
    close_session,
    get_session,
    get_session_history,
    start_session,
)


@pytest.fixture
def database(tmp_path: Path) -> tuple[object, object, Path]:
    database_path = tmp_path / "persistence.sqlite3"
    engine = create_database_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    try:
        yield engine, factory, database_path
    finally:
        engine.dispose()


def _request(session_id: UUID, text: str, timestamp: datetime) -> CustomerRequest:
    return CustomerRequest(
        session_id=session_id,
        trace_id=uuid4(),
        timestamp=timestamp,
        channel_type=ChannelType.TEXT_WEB,
        modality=InputModality.TEXT,
        message_text=text,
    )


def test_session_creation_persists_disclosure_and_started_audit(database) -> None:
    _, factory, _ = database
    with factory() as db:
        conversation = start_session(db, channel_type=ChannelType.TEXT_WEB.value)
        history = get_session_history(db, UUID(conversation.id))

    assert conversation.status == SessionStatus.ACTIVE.value
    assert conversation.started_at.tzinfo is not None
    assert conversation.started_at.utcoffset() == timedelta(0)
    assert len(history.messages) == 1
    assert history.messages[0].role == MessageRole.ASSISTANT.value
    assert "automated assistant" in history.messages[0].text
    assert [event.action for event in history.audit_events] == ["session.started"]


def test_messages_persist_in_sequence_and_order(database) -> None:
    _, factory, _ = database
    with factory() as db:
        conversation = start_session(db, channel_type=ChannelType.TEXT_WEB.value)
        session_id = UUID(conversation.id)
        append_customer_message(
            db,
            session_id=session_id,
            request=_request(
                session_id,
                "first",
                datetime(2026, 10, 25, 12, 0, tzinfo=timezone(timedelta(hours=5))),
            ),
        )
        append_customer_message(
            db,
            session_id=session_id,
            request=_request(
                session_id,
                "second",
                datetime(2026, 10, 25, 7, 1, tzinfo=UTC),
            ),
        )
        history = get_session_history(db, session_id)

    assert [message.sequence for message in history.messages] == [1, 2, 3, 4, 5]
    assert [message.role for message in history.messages] == [
        "assistant",
        "customer",
        "assistant",
        "customer",
        "assistant",
    ]
    assert [message.text for message in history.messages[1::2]] == [
        "first",
        "second",
    ]
    assert history.messages[1].timestamp == datetime(2026, 10, 25, 7, 0, tzinfo=UTC)


def test_session_close_persists_outcome_and_audit(database) -> None:
    _, factory, _ = database
    with factory() as db:
        conversation = start_session(db, channel_type=ChannelType.TEXT_WEB.value)
        session_id = UUID(conversation.id)
        closed = close_session(
            db,
            session_id=session_id,
            outcome=SessionOutcome.UNRESOLVED,
        )
        history = get_session_history(db, session_id)

    assert closed.status == SessionStatus.CLOSED.value
    assert closed.ended_at is not None
    assert closed.outcome == SessionOutcome.UNRESOLVED.value
    assert [event.action for event in history.audit_events] == [
        "session.started",
        "session.ended",
    ]
    assert history.audit_events[-1].outcome == "unresolved"


def test_unknown_session_is_rejected(database) -> None:
    _, factory, _ = database
    with factory() as db, pytest.raises(SessionNotFoundError):
        get_session(db, uuid4())


def test_closed_session_rejects_new_messages_and_duplicate_close(database) -> None:
    _, factory, _ = database
    with factory() as db:
        conversation = start_session(db, channel_type=ChannelType.TEXT_WEB.value)
        session_id = UUID(conversation.id)
        close_session(
            db,
            session_id=session_id,
            outcome=SessionOutcome.CANCELLED,
        )
        with pytest.raises(SessionClosedError):
            append_customer_message(
                db,
                session_id=session_id,
                request=_request(
                    session_id,
                    "late message",
                    datetime.now(UTC),
                ),
            )
        with pytest.raises(SessionAlreadyClosedError):
            close_session(
                db,
                session_id=session_id,
                outcome=SessionOutcome.CANCELLED,
            )


def test_foreign_keys_reject_orphaned_messages_and_audits(database) -> None:
    _, factory, _ = database
    with factory() as db:
        db.add(
            Message(
                id=str(uuid4()),
                session_id=str(uuid4()),
                sequence=1,
                role=MessageRole.CUSTOMER.value,
                text="orphan",
                timestamp=datetime.now(UTC),
                modality=InputModality.TEXT.value,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(
            AuditEvent(
                id=str(uuid4()),
                session_id=str(uuid4()),
                trace_id=str(uuid4()),
                actor="system",
                action="test.orphan",
                resource_type="conversation_session",
                outcome="failure",
                timestamp=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_data_survives_engine_disposal_and_separate_connection(database) -> None:
    engine, factory, database_path = database
    with factory() as db:
        conversation = start_session(db, channel_type=ChannelType.MOCK_CALL.value)
        session_id = UUID(conversation.id)
        append_customer_message(
            db,
            session_id=session_id,
            request=CustomerRequest(
                session_id=session_id,
                trace_id=uuid4(),
                timestamp=datetime.now(UTC),
                channel_type=ChannelType.MOCK_CALL,
                modality=InputModality.TEXT,
                message_text="persist me",
            ),
        )

    engine.dispose()
    reopened_engine = create_database_engine(
        f"sqlite:///{database_path.as_posix()}"
    )
    try:
        reopened_factory = create_session_factory(reopened_engine)
        with reopened_factory() as reopened_db:
            history = get_session_history(reopened_db, session_id)
    finally:
        reopened_engine.dispose()

    assert [message.text for message in history.messages] == [
        "I am an automated assistant. Text messages in this demo are stored "
        "to support the conversation.",
        "persist me",
        "Your message was recorded. Automated response generation is not "
        "implemented yet.",
    ]
    assert len(history.audit_events) == 3


def test_database_operations_do_not_mutate_canonical_fixture(database) -> None:
    original_bytes = CANONICAL_FIXTURE_PATH.read_bytes()
    _, factory, _ = database
    with factory() as db:
        conversation = start_session(db, channel_type=ChannelType.TEXT_WEB.value)
        append_customer_message(
            db,
            session_id=UUID(conversation.id),
            request=_request(
                UUID(conversation.id),
                "test-only text",
                datetime.now(UTC),
            ),
        )
        close_session(
            db,
            session_id=UUID(conversation.id),
            outcome=SessionOutcome.UNRESOLVED,
        )
    assert CANONICAL_FIXTURE_PATH.read_bytes() == original_bytes


def test_database_constraints_require_consistent_session_lifecycle(database) -> None:
    _, factory, _ = database
    with factory() as db:
        db.add(
            ConversationSession(
                id=str(uuid4()),
                channel=ChannelType.TEXT_WEB.value,
                started_at=datetime.now(UTC),
                status=SessionStatus.CLOSED.value,
                consent_state="unknown",
                auth_state="anonymous",
                outcome=None,
                start_trace_id=str(uuid4()),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_persistence_has_no_unneeded_customer_or_audio_columns() -> None:
    assert "customer_id" not in ConversationSession.__table__.columns
    assert "raw_audio" not in Message.__table__.columns
    assert "credentials" not in Message.__table__.columns
