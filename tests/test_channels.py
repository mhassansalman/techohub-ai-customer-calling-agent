from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.channels import (
    AgentResponse,
    BrowserVoiceChannelAdapter,
    ChannelAdapter,
    ChannelError,
    ChannelErrorCode,
    ChannelEventType,
    ChannelMetadataEntry,
    ChannelType,
    CustomerRequest,
    DeliveryResult,
    DeliveryStatus,
    InboundChannelEvent,
    InputModality,
    MockCallChannelAdapter,
    TelephonyChannelAdapter,
    TextWebChannelAdapter,
    UnsupportedChannelOperation,
    normalize_inbound_event,
)

SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")
TRACE_ID = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


class ContractTestAdapter:
    def __init__(self, channel_type: ChannelType) -> None:
        self.channel_type = channel_type

    def normalize(self, event: InboundChannelEvent) -> CustomerRequest | None:
        return normalize_inbound_event(event, expected_channel=self.channel_type)

    async def deliver(self, response: AgentResponse) -> DeliveryResult:
        if response.channel_type is not self.channel_type:
            raise ValueError("response channel does not match adapter")
        return DeliveryResult(
            session_id=response.session_id,
            trace_id=response.trace_id,
            channel_type=self.channel_type,
            status=DeliveryStatus.SENT,
        )


def make_message_event(
    channel_type: ChannelType = ChannelType.TEXT_WEB,
    *,
    modality: InputModality = InputModality.TEXT,
    message_text: str = "Hello",
    **overrides: object,
) -> InboundChannelEvent:
    return InboundChannelEvent(
        channel_type=channel_type,
        event_type=ChannelEventType.MESSAGE,
        session_id=SESSION_ID,
        trace_id=TRACE_ID,
        timestamp=NOW,
        modality=modality,
        message_text=message_text,
        **overrides,
    )


@pytest.mark.parametrize(
    ("channel", "protocol"),
    [
        (ChannelType.TEXT_WEB, TextWebChannelAdapter),
        (ChannelType.BROWSER_VOICE, BrowserVoiceChannelAdapter),
        (ChannelType.MOCK_CALL, MockCallChannelAdapter),
    ],
)
def test_four_channel_contracts_normalize_and_correlate(
    channel: ChannelType, protocol: type[ChannelAdapter]
) -> None:
    adapter = ContractTestAdapter(channel)
    event = make_message_event(channel)

    normalized = adapter.normalize(event)

    assert isinstance(adapter, protocol)
    assert normalized is not None
    assert normalized.channel_type is channel
    assert normalized.session_id == SESSION_ID
    assert normalized.trace_id == TRACE_ID
    assert normalized.message_text == "Hello"
    assert normalized.timestamp == NOW


def test_browser_voice_transcript_preserves_speech_metadata() -> None:
    event = make_message_event(
        ChannelType.BROWSER_VOICE,
        modality=InputModality.SPEECH_TRANSCRIPT,
        message_text="I need an appointment",
        language="en",
        asr_confidence=0.91,
        channel_metadata=(ChannelMetadataEntry(key="source", value="browser"),),
    )

    request = normalize_inbound_event(
        event, expected_channel=ChannelType.BROWSER_VOICE
    )

    assert request is not None
    assert request.modality is InputModality.SPEECH_TRANSCRIPT
    assert request.asr_confidence == 0.91
    assert request.channel_metadata[0].value == "browser"


def test_lifecycle_events_do_not_become_customer_messages() -> None:
    event = InboundChannelEvent(
        channel_type=ChannelType.MOCK_CALL,
        event_type=ChannelEventType.SESSION_STARTED,
        session_id=SESSION_ID,
        trace_id=TRACE_ID,
        timestamp=NOW,
    )

    assert normalize_inbound_event(
        event, expected_channel=ChannelType.MOCK_CALL
    ) is None


def test_untranscribed_audio_is_explicitly_unsupported() -> None:
    event = InboundChannelEvent(
        channel_type=ChannelType.BROWSER_VOICE,
        event_type=ChannelEventType.AUDIO,
        session_id=SESSION_ID,
        trace_id=TRACE_ID,
        timestamp=NOW,
        modality=InputModality.AUDIO,
    )

    with pytest.raises(UnsupportedChannelOperation, match="must be transcribed"):
        normalize_inbound_event(
            event, expected_channel=ChannelType.BROWSER_VOICE
        )


def test_adapter_rejects_wrong_channel() -> None:
    event = make_message_event(ChannelType.TEXT_WEB)

    with pytest.raises(ValueError, match="Expected 'browser_voice'"):
        normalize_inbound_event(
            event, expected_channel=ChannelType.BROWSER_VOICE
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "channel_type": "text_web",
            "event_type": "message",
            "session_id": str(SESSION_ID),
            "trace_id": str(TRACE_ID),
            "timestamp": NOW.isoformat(),
            "modality": "text",
            "message_text": "   ",
        },
        {
            "channel_type": "text_web",
            "event_type": "message",
            "session_id": str(SESSION_ID),
            "trace_id": str(TRACE_ID),
            "timestamp": NOW.isoformat(),
            "modality": "speech_transcript",
            "message_text": "Hello",
        },
        {
            "channel_type": "telephony",
            "event_type": "message",
            "session_id": str(SESSION_ID),
            "trace_id": str(TRACE_ID),
            "timestamp": NOW.isoformat(),
            "modality": "audio",
        },
    ],
)
def test_invalid_inbound_events_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InboundChannelEvent.model_validate(payload)


def test_normalized_request_rejects_naive_timestamp_and_blank_text() -> None:
    with pytest.raises(ValidationError):
        CustomerRequest(
            session_id=SESSION_ID,
            trace_id=TRACE_ID,
            timestamp=datetime(2030, 1, 2, 3, 4, 5),
            channel_type=ChannelType.TEXT_WEB,
            modality=InputModality.TEXT,
            message_text="Hello",
        )
    with pytest.raises(ValidationError):
        CustomerRequest(
            session_id=SESSION_ID,
            trace_id=TRACE_ID,
            timestamp=NOW,
            channel_type=ChannelType.TEXT_WEB,
            modality=InputModality.TEXT,
            message_text=" ",
        )


def test_delivery_error_must_be_explicit_on_failure() -> None:
    with pytest.raises(ValidationError):
        DeliveryResult(
            session_id=SESSION_ID,
            trace_id=TRACE_ID,
            channel_type=ChannelType.TEXT_WEB,
            status=DeliveryStatus.FAILED,
        )

    failed = DeliveryResult(
        session_id=SESSION_ID,
        trace_id=TRACE_ID,
        channel_type=ChannelType.TEXT_WEB,
        status=DeliveryStatus.FAILED,
        error=ChannelError(
            code=ChannelErrorCode.DELIVERY_FAILED,
            message="TEST ONLY delivery failure",
            retryable=True,
        ),
    )
    assert failed.error is not None
    assert failed.error.code is ChannelErrorCode.DELIVERY_FAILED


@pytest.mark.asyncio
async def test_test_double_delivers_response_with_correlation_ids() -> None:
    adapter = ContractTestAdapter(ChannelType.MOCK_CALL)
    response = AgentResponse(
        session_id=SESSION_ID,
        trace_id=TRACE_ID,
        timestamp=NOW,
        channel_type=ChannelType.MOCK_CALL,
        message_text="TEST ONLY response",
    )

    result = await adapter.deliver(response)

    assert result.status is DeliveryStatus.SENT
    assert result.session_id == SESSION_ID
    assert result.trace_id == TRACE_ID


def test_telephony_contract_is_only_a_protocol() -> None:
    assert getattr(TelephonyChannelAdapter, "_is_protocol", False)
    assert "channel_type" in TelephonyChannelAdapter.__annotations__
