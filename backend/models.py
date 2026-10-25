from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base, UTCDateTime


class SessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class SessionOutcome(StrEnum):
    ANSWERED = "answered"
    BOOKED = "booked"
    ESCALATED = "escalated"
    UNRESOLVED = "unresolved"
    DISCONNECTED = "disconnected"
    CANCELLED = "cancelled"
    FAILED = "failed"


class MessageRole(StrEnum):
    CUSTOMER = "customer"
    ASSISTANT = "assistant"


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"
    __table_args__ = (
        CheckConstraint(
            "(status = 'active' AND ended_at IS NULL AND outcome IS NULL) OR "
            "(status = 'closed' AND ended_at IS NOT NULL AND outcome IS NOT NULL)",
            name="ck_session_lifecycle_consistency",
        ),
        Index("ix_conversation_sessions_started_at", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SessionStatus.ACTIVE.value
    )
    consent_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown"
    )
    auth_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="anonymous"
    )
    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    start_trace_id: Mapped[str] = mapped_column(String(36), nullable=False)

    messages: Mapped[list[Message]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.sequence",
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AuditEvent.timestamp",
    )
    availability_context: Mapped[AvailabilityConversationContext | None] = (
        relationship(
            back_populates="session",
            cascade="all, delete-orphan",
            uselist=False,
        )
    )


class AvailabilityConversationContext(Base):
    __tablename__ = "availability_conversation_contexts"
    __table_args__ = (
        CheckConstraint(
            "length(service_id) > 0",
            name="ck_availability_context_service_id",
        ),
        Index("ix_availability_context_updated_at", "updated_at"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    service_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_date: Mapped[date] = mapped_column(Date, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    session: Mapped[ConversationSession] = relationship(
        back_populates="availability_context"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_message_session_sequence"),
        CheckConstraint("length(text) > 0", name="ck_message_text_nonempty"),
        CheckConstraint(
            "asr_confidence IS NULL OR "
            "(asr_confidence >= 0.0 AND asr_confidence <= 1.0)",
            name="ck_message_asr_confidence_range",
        ),
        Index("ix_messages_session_timestamp", "session_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    modality: Mapped[str] = mapped_column(String(24), nullable=False)
    asr_confidence: Mapped[float | None] = mapped_column(nullable=True)

    session: Mapped[ConversationSession] = relationship(back_populates="messages")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_session_timestamp", "session_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor: Mapped[str] = mapped_column(String(24), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    session: Mapped[ConversationSession] = relationship(back_populates="audit_events")
