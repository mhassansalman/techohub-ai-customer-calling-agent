from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChannelType(StrEnum):
    TEXT_WEB = "text_web"
    BROWSER_VOICE = "browser_voice"
    MOCK_CALL = "mock_call"
    TELEPHONY = "telephony"


class InputModality(StrEnum):
    TEXT = "text"
    SPEECH_TRANSCRIPT = "speech_transcript"
    AUDIO = "audio"


class ChannelEventType(StrEnum):
    SESSION_STARTED = "session_started"
    MESSAGE = "message"
    AUDIO = "audio"
    SESSION_ENDED = "session_ended"
    INTERRUPTED = "interrupted"


class ChannelMetadataEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1)
    value: str


class InboundChannelEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    channel_type: ChannelType
    event_type: ChannelEventType
    session_id: UUID
    trace_id: UUID
    timestamp: datetime
    modality: InputModality | None = None
    message_text: str | None = None
    language: str | None = None
    asr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    channel_metadata: tuple[ChannelMetadataEntry, ...] = ()

    @model_validator(mode="after")
    def validate_event_payload(self) -> InboundChannelEvent:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")

        if self.event_type is ChannelEventType.MESSAGE:
            if self.modality not in {
                InputModality.TEXT,
                InputModality.SPEECH_TRANSCRIPT,
            }:
                raise ValueError("message events require text or speech_transcript modality")
            if self.message_text is None or not self.message_text.strip():
                raise ValueError("message events require non-empty message_text")
        elif self.event_type is ChannelEventType.AUDIO:
            if self.modality is not InputModality.AUDIO:
                raise ValueError("audio events require audio modality")
            if self.message_text is not None:
                raise ValueError("raw audio events cannot contain normalized message_text")
        elif self.modality is not None or self.message_text is not None:
            raise ValueError("lifecycle events cannot contain message content")

        if (
            self.channel_type is ChannelType.TEXT_WEB
            and self.modality not in {None, InputModality.TEXT}
        ):
            raise ValueError("text_web only accepts text modality")
        return self


class CustomerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    trace_id: UUID
    timestamp: datetime
    channel_type: ChannelType
    modality: Literal[InputModality.TEXT, InputModality.SPEECH_TRANSCRIPT]
    message_text: str = Field(min_length=1)
    language: str | None = None
    asr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    channel_metadata: tuple[ChannelMetadataEntry, ...] = ()

    @model_validator(mode="after")
    def validate_normalized_request(self) -> CustomerRequest:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if not self.message_text.strip():
            raise ValueError("message_text cannot be blank")
        return self


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    trace_id: UUID
    timestamp: datetime
    channel_type: ChannelType
    message_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_response(self) -> AgentResponse:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if not self.message_text.strip():
            raise ValueError("message_text cannot be blank")
        return self


class ChannelErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    DISCONNECTED = "disconnected"
    DELIVERY_FAILED = "delivery_failed"


class ChannelError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ChannelErrorCode
    message: str = Field(min_length=1)
    retryable: bool


class DeliveryStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"


class DeliveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    trace_id: UUID
    channel_type: ChannelType
    status: DeliveryStatus
    error: ChannelError | None = None

    @model_validator(mode="after")
    def validate_delivery_result(self) -> DeliveryResult:
        if self.status is DeliveryStatus.SENT and self.error is not None:
            raise ValueError("successful delivery cannot contain an error")
        if self.status is DeliveryStatus.FAILED and self.error is None:
            raise ValueError("failed delivery must contain an error")
        return self


class UnsupportedChannelOperation(RuntimeError):
    pass


def normalize_inbound_event(
    event: InboundChannelEvent,
    *,
    expected_channel: ChannelType,
) -> CustomerRequest | None:
    """Convert text-bearing events; leave lifecycle and speech processing to adapters."""
    if event.channel_type is not expected_channel:
        raise ValueError(
            f"Expected {expected_channel.value!r}, received {event.channel_type.value!r}"
        )
    if event.event_type in {
        ChannelEventType.SESSION_STARTED,
        ChannelEventType.SESSION_ENDED,
        ChannelEventType.INTERRUPTED,
    }:
        return None
    if event.event_type is ChannelEventType.AUDIO:
        raise UnsupportedChannelOperation(
            "Audio must be transcribed by the channel speech pipeline before normalization"
        )
    if event.modality is InputModality.TEXT:
        modality = InputModality.TEXT
    elif event.modality is InputModality.SPEECH_TRANSCRIPT:
        modality = InputModality.SPEECH_TRANSCRIPT
    else:
        raise ValueError("message event requires a normalized text modality")
    if event.message_text is None or not event.message_text.strip():
        raise ValueError("message event requires non-empty message_text")
    if event.modality is InputModality.SPEECH_TRANSCRIPT and (
        event.asr_confidence is not None
        and not 0.0 <= event.asr_confidence <= 1.0
    ):
        raise ValueError("asr_confidence must be between 0 and 1")

    return CustomerRequest(
        session_id=event.session_id,
        trace_id=event.trace_id,
        timestamp=event.timestamp,
        channel_type=event.channel_type,
        modality=modality,
        message_text=event.message_text,
        language=event.language,
        asr_confidence=event.asr_confidence,
        channel_metadata=event.channel_metadata,
    )


@runtime_checkable
class ChannelAdapter(Protocol):
    channel_type: ChannelType

    def normalize(self, event: InboundChannelEvent) -> CustomerRequest | None: ...

    async def deliver(self, response: AgentResponse) -> DeliveryResult: ...


@runtime_checkable
class TextWebChannelAdapter(ChannelAdapter, Protocol):
    channel_type: Literal[ChannelType.TEXT_WEB]


@runtime_checkable
class BrowserVoiceChannelAdapter(ChannelAdapter, Protocol):
    channel_type: Literal[ChannelType.BROWSER_VOICE]


@runtime_checkable
class MockCallChannelAdapter(ChannelAdapter, Protocol):
    channel_type: Literal[ChannelType.MOCK_CALL]


@runtime_checkable
class TelephonyChannelAdapter(ChannelAdapter, Protocol):
    channel_type: Literal[ChannelType.TELEPHONY]
