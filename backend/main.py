from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import Generator
from typing import AsyncIterator
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Path, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.availability import AvailabilityConversationService
from backend.channels import ChannelType, CustomerRequest
from backend.database import (
    Base,
    create_database_engine,
    create_session_factory,
    database_session_dependency,
)
from backend.intent import (
    ClassifierConfig,
    GroqClassificationAdapter,
    IntentClassifier,
    RuleFirstIntentClassifier,
)
from backend.knowledge import KnowledgeService
from backend.models import AuditEvent, ConversationSession, Message, SessionStatus
from backend.schemas import (
    MessageResponse,
    SessionEndRequest,
    SessionMessageResponse,
    SessionStartRequest,
    SessionStartResponse,
    SessionStatusResponse,
)
from backend.session_service import (
    ASSISTANT_DISCLOSURE,
    SessionAlreadyClosedError,
    SessionClosedError,
    SessionNotFoundError,
    close_session,
    get_session,
    persist_assistant_message,
    persist_customer_message,
    start_session,
)
from backend.workflow import ConversationWorkflow, WorkflowExecutionError


logger = logging.getLogger(__name__)
WORKFLOW_FAILURE_RESPONSE = (
    "I couldn't safely complete that request right now. Your message was "
    "recorded; please try again later."
)


def _session_status_response(
    db: Session, conversation: ConversationSession
) -> SessionStatusResponse:
    message_count = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.session_id == conversation.id)
    )
    audit_count = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.session_id == conversation.id)
    )
    return SessionStatusResponse(
        session_id=UUID(conversation.id),
        channel_type=ChannelType(conversation.channel),
        status=SessionStatus(conversation.status),
        started_at=conversation.started_at,
        ended_at=conversation.ended_at,
        outcome=conversation.outcome,
        message_count=message_count or 0,
        audit_event_count=audit_count or 0,
    )


def _message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        message_id=UUID(message.id),
        session_id=UUID(message.session_id),
        sequence=message.sequence,
        role=message.role,
        text=message.text,
        timestamp=message.timestamp,
        modality=message.modality,
        language=message.language,
        asr_confidence=message.asr_confidence,
    )


def create_app(
    database_url: str | None = None,
    *,
    workflow: ConversationWorkflow | None = None,
    classifier: IntentClassifier | None = None,
) -> FastAPI:
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="TECHOHUB AI Customer Calling Agent",
        lifespan=lifespan,
    )
    app.state.database_engine = engine
    app.state.session_factory = session_factory
    if workflow is not None and classifier is not None:
        raise ValueError("pass either workflow or classifier, not both")
    app.state.conversation_workflow = workflow or ConversationWorkflow(
        classifier=classifier
        or RuleFirstIntentClassifier(
            GroqClassificationAdapter(ClassifierConfig.from_environment())
        ),
        knowledge=KnowledgeService(),
        availability=AvailabilityConversationService(),
    )

    def get_db() -> Generator[Session, None, None]:
        yield from database_session_dependency(app.state.session_factory)

    @app.post(
        "/api/sessions",
        response_model=SessionStartResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_session(
        payload: SessionStartRequest,
        db: Session = Depends(get_db),
    ) -> SessionStartResponse:
        conversation = start_session(
            db, channel_type=payload.channel_type.value
        )
        return SessionStartResponse(
            session=_session_status_response(db, conversation),
            assistant_disclosure=ASSISTANT_DISCLOSURE,
        )

    @app.get(
        "/api/sessions/{session_id}",
        response_model=SessionStatusResponse,
    )
    def read_session_status(
        session_id: UUID = Path(),
        db: Session = Depends(get_db),
    ) -> SessionStatusResponse:
        try:
            conversation = get_session(db, session_id)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found.",
            ) from error
        return _session_status_response(db, conversation)

    @app.post(
        "/api/sessions/{session_id}/messages",
        response_model=SessionMessageResponse,
    )
    def create_message(
        payload: CustomerRequest,
        session_id: UUID = Path(),
        db: Session = Depends(get_db),
    ) -> SessionMessageResponse:
        if payload.session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Request session_id must match the URL session_id.",
            )
        try:
            customer_message = persist_customer_message(
                db,
                session_id=session_id,
                request=payload,
            )
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found.",
            ) from error
        except SessionClosedError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Session is closed.",
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error

        try:
            workflow_result = asyncio.run(
                app.state.conversation_workflow.run(
                    session_id=session_id,
                    request=payload,
                    db=db,
                )
            )
            response_text = workflow_result.response_text
            outcome = workflow_result.outcome
        except WorkflowExecutionError as error:
            logger.error(
                "Conversation workflow failed for session %s (%s)",
                session_id,
                type(error.__cause__).__name__ if error.__cause__ else "unknown",
            )
            response_text = WORKFLOW_FAILURE_RESPONSE
            outcome = "failed"

        try:
            assistant_message = persist_assistant_message(
                db,
                session_id=session_id,
                trace_id=payload.trace_id,
                text=response_text,
                outcome=outcome,
            )
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found.",
            ) from error
        except SessionClosedError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Session is closed.",
            ) from error

        return SessionMessageResponse(
            customer_message=_message_response(customer_message),
            assistant_message=_message_response(assistant_message),
        )

    @app.post(
        "/api/sessions/{session_id}/end",
        response_model=SessionStatusResponse,
    )
    def end_session(
        payload: SessionEndRequest,
        session_id: UUID = Path(),
        db: Session = Depends(get_db),
    ) -> SessionStatusResponse:
        try:
            conversation = close_session(
                db,
                session_id=session_id,
                outcome=payload.outcome,
            )
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found.",
            ) from error
        except SessionAlreadyClosedError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Session is already closed.",
            ) from error
        return _session_status_response(db, conversation)

    return app


app = create_app()
