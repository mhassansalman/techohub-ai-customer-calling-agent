from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.channels import CustomerRequest, InputModality
from backend.database import utc_now
from backend.models import (
    AuditEvent,
    ConversationSession,
    Message,
    MessageRole,
    SessionOutcome,
    SessionStatus,
)

ASSISTANT_DISCLOSURE = (
    "I am an automated assistant. Text messages in this demo are stored "
    "to support the conversation."
)
INTERIM_RESPONSE = (
    "Your message was recorded. Automated response generation is not "
    "implemented yet."
)


class SessionNotFoundError(LookupError):
    pass


class SessionClosedError(RuntimeError):
    pass


class SessionAlreadyClosedError(RuntimeError):
    pass


def _audit(
    *,
    session_id: str,
    trace_id: str,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    outcome: str,
) -> AuditEvent:
    return AuditEvent(
        session_id=session_id,
        trace_id=trace_id,
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        timestamp=utc_now(),
    )


def start_session(db: Session, *, channel_type: str) -> ConversationSession:
    now = utc_now()
    session_id = str(uuid4())
    trace_id = str(uuid4())
    conversation = ConversationSession(
        id=session_id,
        channel=channel_type,
        started_at=now,
        status=SessionStatus.ACTIVE.value,
        consent_state="unknown",
        auth_state="anonymous",
        start_trace_id=trace_id,
    )
    disclosure = Message(
        id=str(uuid4()),
        session_id=session_id,
        sequence=1,
        role=MessageRole.ASSISTANT.value,
        text=ASSISTANT_DISCLOSURE,
        timestamp=now,
        modality="system",
    )
    db.add_all(
        [
            conversation,
            disclosure,
            _audit(
                session_id=session_id,
                trace_id=trace_id,
                actor="system",
                action="session.started",
                resource_type="conversation_session",
                resource_id=session_id,
                outcome="success",
            ),
        ]
    )
    db.commit()
    db.refresh(conversation)
    return conversation


def get_session(db: Session, session_id: UUID) -> ConversationSession:
    conversation = db.get(ConversationSession, str(session_id))
    if conversation is None:
        raise SessionNotFoundError(str(session_id))
    return conversation


def get_session_history(
    db: Session, session_id: UUID
) -> ConversationSession:
    statement = (
        select(ConversationSession)
        .where(ConversationSession.id == str(session_id))
        .options(
            selectinload(ConversationSession.messages),
            selectinload(ConversationSession.audit_events),
        )
    )
    conversation = db.scalar(statement)
    if conversation is None:
        raise SessionNotFoundError(str(session_id))
    return conversation


def append_customer_message(
    db: Session,
    *,
    session_id: UUID,
    request: CustomerRequest,
) -> tuple[Message, Message]:
    conversation = get_session(db, session_id)
    if conversation.status != SessionStatus.ACTIVE.value:
        raise SessionClosedError(str(session_id))
    if request.session_id != session_id:
        raise ValueError("request session_id does not match the URL session_id")
    if request.channel_type.value != conversation.channel:
        raise ValueError("request channel does not match the session channel")

    next_sequence = db.scalar(
        select(func.max(Message.sequence)).where(Message.session_id == str(session_id))
    )
    sequence = (next_sequence or 0) + 1
    customer_message = Message(
        id=str(uuid4()),
        session_id=str(session_id),
        sequence=sequence,
        role=MessageRole.CUSTOMER.value,
        text=request.message_text,
        timestamp=request.timestamp,
        language=request.language,
        modality=request.modality.value,
        asr_confidence=request.asr_confidence,
    )
    assistant_message = Message(
        id=str(uuid4()),
        session_id=str(session_id),
        sequence=sequence + 1,
        role=MessageRole.ASSISTANT.value,
        text=INTERIM_RESPONSE,
        timestamp=utc_now(),
        modality=InputModality.TEXT.value,
    )
    db.add_all(
        [
            customer_message,
            assistant_message,
            _audit(
                session_id=str(session_id),
                trace_id=str(request.trace_id),
                actor=MessageRole.CUSTOMER.value,
                action="message.received",
                resource_type="message",
                resource_id=customer_message.id,
                outcome="success",
            ),
            _audit(
                session_id=str(session_id),
                trace_id=str(request.trace_id),
                actor="system",
                action="assistant.response_pending",
                resource_type="message",
                resource_id=assistant_message.id,
                outcome="not_implemented",
            ),
        ]
    )
    db.commit()
    db.refresh(customer_message)
    db.refresh(assistant_message)
    return customer_message, assistant_message


def persist_customer_message(
    db: Session,
    *,
    session_id: UUID,
    request: CustomerRequest,
) -> Message:
    conversation = get_session(db, session_id)
    if conversation.status != SessionStatus.ACTIVE.value:
        raise SessionClosedError(str(session_id))
    _validate_message_session(conversation, session_id, request)

    next_sequence = db.scalar(
        select(func.max(Message.sequence)).where(Message.session_id == str(session_id))
    )
    customer_message = Message(
        id=str(uuid4()),
        session_id=str(session_id),
        sequence=(next_sequence or 0) + 1,
        role=MessageRole.CUSTOMER.value,
        text=request.message_text,
        timestamp=request.timestamp,
        language=request.language,
        modality=request.modality.value,
        asr_confidence=request.asr_confidence,
    )
    db.add_all(
        [
            customer_message,
            _audit(
                session_id=str(session_id),
                trace_id=str(request.trace_id),
                actor=MessageRole.CUSTOMER.value,
                action="message.received",
                resource_type="message",
                resource_id=customer_message.id,
                outcome="success",
            ),
        ]
    )
    db.commit()
    db.refresh(customer_message)
    return customer_message


def persist_assistant_message(
    db: Session,
    *,
    session_id: UUID,
    trace_id: UUID,
    text: str,
    outcome: str,
) -> Message:
    conversation = get_session(db, session_id)
    if conversation.status != SessionStatus.ACTIVE.value:
        raise SessionClosedError(str(session_id))
    if not text.strip():
        raise ValueError("assistant response cannot be blank")

    next_sequence = db.scalar(
        select(func.max(Message.sequence)).where(Message.session_id == str(session_id))
    )
    assistant_message = Message(
        id=str(uuid4()),
        session_id=str(session_id),
        sequence=(next_sequence or 0) + 1,
        role=MessageRole.ASSISTANT.value,
        text=text,
        timestamp=utc_now(),
        modality=InputModality.TEXT.value,
    )
    db.add_all(
        [
            assistant_message,
            _audit(
                session_id=str(session_id),
                trace_id=str(trace_id),
                actor="system",
                action="assistant.response_delivered",
                resource_type="message",
                resource_id=assistant_message.id,
                outcome=outcome,
            ),
        ]
    )
    db.commit()
    db.refresh(assistant_message)
    return assistant_message


def _validate_message_session(
    conversation: ConversationSession,
    session_id: UUID,
    request: CustomerRequest,
) -> None:
    if request.session_id != session_id:
        raise ValueError("request session_id does not match the URL session_id")
    if request.channel_type.value != conversation.channel:
        raise ValueError("request channel does not match the session channel")


def close_session(
    db: Session,
    *,
    session_id: UUID,
    outcome: SessionOutcome,
) -> ConversationSession:
    conversation = get_session(db, session_id)
    if conversation.status != SessionStatus.ACTIVE.value:
        raise SessionAlreadyClosedError(str(session_id))

    now = utc_now()
    conversation.status = SessionStatus.CLOSED.value
    conversation.ended_at = now
    conversation.outcome = outcome.value
    db.add(
        _audit(
            session_id=str(session_id),
            trace_id=conversation.start_trace_id,
            actor="customer",
            action="session.ended",
            resource_type="conversation_session",
            resource_id=str(session_id),
            outcome=outcome.value,
        )
    )
    db.commit()
    db.refresh(conversation)
    return conversation
