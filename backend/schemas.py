from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.channels import ChannelType, InputModality
from backend.models import MessageRole, SessionOutcome, SessionStatus


SUPPORTED_SESSION_CHANNELS = {
    ChannelType.TEXT_WEB,
    ChannelType.BROWSER_VOICE,
    ChannelType.MOCK_CALL,
}


class SessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel_type: ChannelType = ChannelType.TEXT_WEB

    @model_validator(mode="after")
    def validate_channel(self) -> SessionStartRequest:
        if self.channel_type not in SUPPORTED_SESSION_CHANNELS:
            raise ValueError("telephony session creation is not implemented")
        return self


class SessionEndRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: SessionOutcome


class MessageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    message_id: UUID
    session_id: UUID
    sequence: int
    role: MessageRole
    text: str
    timestamp: datetime
    modality: InputModality | Literal["system"]
    language: str | None = None
    asr_confidence: float | None = None


class SessionStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: UUID
    channel_type: ChannelType
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None
    outcome: SessionOutcome | None
    message_count: int = Field(ge=0)
    audit_event_count: int = Field(ge=0)


class SessionStartResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    session: SessionStatusResponse
    assistant_disclosure: str


class SessionMessageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    customer_message: MessageResponse
    assistant_message: MessageResponse
