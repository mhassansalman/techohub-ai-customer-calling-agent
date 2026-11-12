from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from collections.abc import Generator
from typing import AsyncIterator
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session

from backend.availability import AvailabilityConversationService
from backend.channels import ChannelType, CustomerRequest
from backend.chunker import load_approved_chunks
from backend.database import (
    Base,
    create_database_engine,
    create_session_factory,
    database_session_dependency,
    is_postgresql_url,
)
from backend.fixtures import load_demo_salon_fixture
from backend.intent import (
    ClassifierConfig,
    GroqClassificationAdapter,
    IntentClassifier,
    RuleFirstIntentClassifier,
)
from backend.knowledge import KnowledgeService
from backend.rag import RagConfig, RagRetriever, SemanticRetriever, SentenceTransformerProvider
from backend.models import (
    AuditEvent,
    ConversationSession,
    HandoffTicket,
    Message,
    SessionStatus,
)
from backend.schemas import (
    MessageResponse,
    ServiceCatalogItem,
    SessionEndRequest,
    SessionMessageResponse,
    SessionStartRequest,
    SessionStartResponse,
    SessionStatusResponse,
    StaffTicketResponse,
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
from backend.mcp_client import McpConfig


logger = logging.getLogger(__name__)
WORKFLOW_FAILURE_RESPONSE = (
    "I couldn't safely complete that request right now. Your message was "
    "recorded; please try again later."
)

SESSION_TOKEN_HEADER = "X-Session-Token"


def _cors_allow_origins() -> list[str]:
    """Parse comma-separated allowed origins from configuration.

    Defaults to allowing no cross-origin browser traffic. Render operators set
    TECHOHUB_CORS_ORIGINS to the public frontend origin(s) (e.g. the Vercel
    Hobby URL). Never allow ``*`` for session-scoped endpoints in production.
    """
    raw = os.getenv("TECHOHUB_CORS_ORIGINS", "").strip()
    if not raw:
        return []
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if "*" in origins:
        raise ValueError("TECHOHUB_CORS_ORIGINS must not contain a wildcard.")
    return origins


def require_session_access_token(
    conversation: ConversationSession,
    x_session_token: str | None = Header(default=None, alias=SESSION_TOKEN_HEADER),
) -> None:
    """Reject session-scoped requests that lack a valid per-session access token.

    The session UUID alone must not authorize reads, writes, or termination: a
    bearer token issued at session start is required on every session-specific
    operation so that knowing (or guessing) a UUID is insufficient to touch
    another customer's conversation.
    """
    provided = (x_session_token or "").encode("utf-8")
    expected = (conversation.access_token or "").encode("utf-8")
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session access token is required or invalid.",
        )


def require_staff_api_key(
    x_staff_api_key: str | None = Header(default=None, alias="X-Staff-API-Key"),
) -> None:
    configured_key = os.getenv("STAFF_API_KEY")
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Staff ticket service is not configured.",
        )
    if not x_staff_api_key or not secrets.compare_digest(
        configured_key.encode("utf-8"),
        x_staff_api_key.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staff authentication required.",
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
    is_vercel = bool(os.getenv("VERCEL"))
    resolved_database_url = database_url or os.getenv("DATABASE_URL") or None
    if is_vercel:
        if not resolved_database_url:
            raise RuntimeError(
                "DATABASE_URL is required on Vercel. Set it to the Neon "
                "PostgreSQL connection string in the project environment variables."
            )
        try:
            is_postgresql = is_postgresql_url(resolved_database_url)
        except ArgumentError:
            is_postgresql = False
        if not is_postgresql:
            raise RuntimeError(
                "DATABASE_URL must be a valid PostgreSQL connection string on Vercel."
            ) from None
    allowed_origins = _cors_allow_origins()
    mcp_enabled = McpConfig.from_environment().enabled and not is_vercel
    engine = create_database_engine(resolved_database_url)
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
    if workflow is None:
        rag_config = RagConfig.from_environment()
        lexical_retriever = RagRetriever() if rag_config.enabled else None
        semantic_retriever = None
        if (
            not is_vercel
            and rag_config.enabled
            and rag_config.provider in {"semantic", "auto"}
        ):
            try:
                semantic_retriever = SemanticRetriever(
                    index=load_approved_chunks(),
                    provider=SentenceTransformerProvider(),
                )
            except Exception:
                # Semantic provider unavailable; fall back to lexical only.
                semantic_retriever = None
        if (
            not is_vercel
            and rag_config.enabled
            and rag_config.provider == "semantic"
            and semantic_retriever is None
        ):
            # Semantic was explicitly requested but unavailable; degrade to lexical.
            semantic_retriever = None
    else:
        rag_config = None
        lexical_retriever = None
        semantic_retriever = None
    if workflow is not None and classifier is not None:
        raise ValueError("pass either workflow or classifier, not both")
    app.state.conversation_workflow = workflow or ConversationWorkflow(
        classifier=classifier
        or RuleFirstIntentClassifier(
            GroqClassificationAdapter(ClassifierConfig.from_environment())
        ),
        knowledge=KnowledgeService(),
        availability=AvailabilityConversationService(),
        rag_retriever=semantic_retriever,
        lexical_retriever=lexical_retriever,
        semantic_retriever=semantic_retriever,
        rag_enabled=rag_config.enabled if rag_config else False,
        rag_provider=(
            "lexical"
            if is_vercel and rag_config and rag_config.provider in {"semantic", "auto"}
            else rag_config.provider if rag_config else "lexical"
        ),
        mcp_enabled=mcp_enabled,
    )

    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Accept", SESSION_TOKEN_HEADER],
        )

    def get_db() -> Generator[Session, None, None]:
        yield from database_session_dependency(app.state.session_factory)

    @app.get(
        "/health",
        include_in_schema=False,
    )
    def health_check():
        return {"status": "ok"}

    @app.get(
        "/api/services",
        response_model=list[ServiceCatalogItem],
    )
    def list_services() -> list[ServiceCatalogItem]:
        try:
            fixture = load_demo_salon_fixture()
        except (OSError, ValueError) as error:
            logger.error(
                "Approved service catalog could not be loaded (%s)",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Approved service catalog is temporarily unavailable.",
            ) from error
        return [
            ServiceCatalogItem(
                service_id=service.service_id,
                name=service.name,
                price_amount=service.price_amount,
                currency=service.currency,
                duration_minutes=service.duration_minutes,
            )
            for service in fixture.services
            if service.active
        ]

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
            access_token=conversation.access_token,
        )

    @app.get(
        "/api/sessions/{session_id}",
        response_model=SessionStatusResponse,
    )
    def read_session_status(
        session_id: UUID = Path(),
        x_session_token: str | None = Header(default=None, alias=SESSION_TOKEN_HEADER),
        db: Session = Depends(get_db),
    ) -> SessionStatusResponse:
        try:
            conversation = get_session(db, session_id)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found.",
            ) from error
        require_session_access_token(conversation, x_session_token)
        return _session_status_response(db, conversation)

    @app.post(
        "/api/sessions/{session_id}/messages",
        response_model=SessionMessageResponse,
    )
    def create_message(
        payload: CustomerRequest,
        session_id: UUID = Path(),
        x_session_token: str | None = Header(default=None, alias=SESSION_TOKEN_HEADER),
        db: Session = Depends(get_db),
    ) -> SessionMessageResponse:
        if payload.session_id != session_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Request session_id must match the URL session_id.",
            )
        try:
            conversation = get_session(db, session_id)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found.",
            ) from error
        require_session_access_token(conversation, x_session_token)
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
        x_session_token: str | None = Header(default=None, alias=SESSION_TOKEN_HEADER),
        db: Session = Depends(get_db),
    ) -> SessionStatusResponse:
        try:
            conversation = get_session(db, session_id)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found.",
            ) from error
        require_session_access_token(conversation, x_session_token)
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

    @app.get(
        "/api/staff/tickets",
        response_model=list[StaffTicketResponse],
    )
    def list_staff_tickets(
        _: None = Depends(require_staff_api_key),
        db: Session = Depends(get_db),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[StaffTicketResponse]:
        tickets = db.scalars(
            select(HandoffTicket)
            .where(HandoffTicket.status == "queued")
            .order_by(HandoffTicket.created_at.desc(), HandoffTicket.id.desc())
            .limit(limit)
        )
        return [StaffTicketResponse.model_validate(ticket) for ticket in tickets]

    @app.get(
        "/api/staff/tickets/{ticket_id}",
        response_model=StaffTicketResponse,
    )
    def read_staff_ticket(
        ticket_id: UUID = Path(),
        _: None = Depends(require_staff_api_key),
        db: Session = Depends(get_db),
    ) -> StaffTicketResponse:
        ticket = db.get(HandoffTicket, str(ticket_id))
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found.",
            )
        return StaffTicketResponse.model_validate(ticket)

    return app


app = create_app()
