from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from backend.intent import (
    DEFAULT_GROQ_MODEL,
    ClassificationStatus,
    ClassifierConfig,
    ClassifierProviderError,
    ClassifierSource,
    GroqClassificationAdapter,
    Intent,
    ModelClassificationPayload,
    ProviderErrorCode,
    RuleFirstIntentClassifier,
    classify_with_rules,
)


def _payload(
    intents: list[str],
    *,
    service_id: str | None = None,
    requested_date: str | None = None,
    confidence: float = 0.91,
) -> dict[str, Any]:
    return {
        "intents": intents,
        "entities": {
            "service_id": service_id,
            "requested_date": requested_date,
        },
        "confidence": confidence,
    }


def _provider_response(
    payload: dict[str, Any],
    *,
    reasoning: str = "internal provider reasoning",
) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(payload),
                        "reasoning": reasoning,
                    }
                }
            ]
        },
    )


def _adapter(
    handler,
    *,
    max_retries: int = 1,
    sleep_calls: list[float] | None = None,
) -> GroqClassificationAdapter:
    async def sleep(delay: float) -> None:
        if sleep_calls is not None:
            sleep_calls.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GroqClassificationAdapter(
        ClassifierConfig(
            api_key="test-only-not-a-real-key",
            max_retries=max_retries,
            backoff_seconds=0,
        ),
        client=client,
        sleep=sleep,
    )


@pytest.mark.asyncio
async def test_groq_adapter_validates_content_and_ignores_reasoning_field() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == DEFAULT_GROQ_MODEL
        assert body["response_format"] == {"type": "json_object"}
        assert body["temperature"] == 0
        assert request.headers["Authorization"] == "Bearer test-only-not-a-real-key"
        return _provider_response(
            _payload(
                [Intent.APPOINTMENT_AVAILABILITY.value],
                service_id="haircut",
                requested_date="Friday",
            ),
            reasoning="SECRET_TEST_REASONING_DO_NOT_EXPOSE",
        )

    adapter = _adapter(handler)
    try:
        result = await adapter.classify("Do you have a haircut appointment Friday?")
    finally:
        await adapter._client.aclose()

    assert result.intents == (Intent.APPOINTMENT_AVAILABILITY,)
    assert result.entities.service_id == "haircut"
    assert result.entities.requested_date == "Friday"
    assert "SECRET_TEST_REASONING_DO_NOT_EXPOSE" not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '{"intents":["not_a_supported_intent"],"entities":{},"confidence":0.9}',
        '{"intents":["appointment_availability"],"entities":{"tool":"booking"},"confidence":0.9}',
        '{"intents":["appointment_availability"],"entities":{},"confidence":1.01}',
        '{"intents":["appointment_availability"],"entities":{},"confidence":true}',
        '{"intents":["appointment_availability","appointment_availability"],"entities":{},"confidence":0.9}',
    ],
)
async def test_groq_adapter_rejects_invalid_structured_output(content: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    adapter = _adapter(handler, max_retries=0)
    try:
        with pytest.raises(ClassifierProviderError) as caught:
            await adapter.classify("Do you have a haircut appointment Friday?")
    finally:
        await adapter._client.aclose()

    assert caught.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "query"),
    [
        (
            _payload(
                [Intent.APPOINTMENT_AVAILABILITY.value],
                service_id="unknown-service",
                requested_date="Friday",
            ),
            "Do you have a haircut appointment Friday?",
        ),
        (
            _payload(
                [Intent.APPOINTMENT_AVAILABILITY.value],
                service_id="haircut",
                requested_date="Saturday",
            ),
            "Do you have a haircut appointment Friday?",
        ),
        (
            _payload(
                [Intent.APPOINTMENT_AVAILABILITY.value],
                service_id="haircut",
                requested_date="next Friday after lunch",
            ),
            "Do you have a haircut appointment next Friday after lunch?",
        ),
        (
            _payload(
                [Intent.APPOINTMENT_AVAILABILITY.value],
                service_id="haircut",
                requested_date="Friday",
            ),
            "Do you have a haircut appointment next Friday?",
        ),
        (
            _payload(
                [Intent.FAQ_SERVICE_POLICY.value],
                service_id="beard-trim",
            ),
            "How much is a haircut?",
        ),
    ],
)
async def test_groq_adapter_rejects_invented_or_unsupported_entities(
    payload: dict[str, Any],
    query: str,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return _provider_response(payload)

    adapter = _adapter(handler, max_retries=0)
    try:
        with pytest.raises(ClassifierProviderError) as caught:
            await adapter.classify(query)
    finally:
        await adapter._client.aclose()

    assert caught.value.code is ProviderErrorCode.INVALID_RESPONSE


def test_model_output_rejects_extra_fields_and_bad_confidence() -> None:
    with pytest.raises(ValidationError):
        ModelClassificationPayload.model_validate(
            {
                **_payload([Intent.UNSUPPORTED.value]),
                "reasoning": "must not be surfaced",
            }
        )
    with pytest.raises(ValidationError):
        ModelClassificationPayload.model_validate(_payload(["unsupported", "complaint"]))


def test_project_env_config_loads_without_exposing_secret(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'GROQ_API_KEY="test-only-secret-value"\n'
        "GROQ_MODEL=openai/gpt-oss-20b\n"
        "GROQ_TIMEOUT_SECONDS=4.5\n"
        "GROQ_MAX_RETRIES=0\n"
        "GROQ_TOTAL_DEADLINE_SECONDS=6\n"
        "UNRELATED_SECRET=ignore-me\n",
        encoding="utf-8",
    )

    config = ClassifierConfig.from_environment(
        env_file=env_file,
        environ={"GROQ_MODEL": "overridden/model"},
    )

    assert config.api_key == "test-only-secret-value"
    assert config.model == "overridden/model"
    assert config.attempt_timeout_seconds == 4.5
    assert config.max_retries == 0
    assert config.total_deadline_seconds == 6
    assert "test-only-secret-value" not in repr(config)
    assert "ignore-me" not in repr(config)


def test_default_environment_config_does_not_require_key() -> None:
    config = ClassifierConfig.from_environment(
        env_file=Path("missing-test-env"),
        environ={},
    )

    assert config.api_key is None
    assert config.model == DEFAULT_GROQ_MODEL
    assert config.attempt_timeout_seconds == 5
    assert config.max_retries == 1
    assert config.total_deadline_seconds == 8


@pytest.mark.asyncio
async def test_missing_api_key_fails_without_network_request() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _provider_response(_payload([Intent.UNSUPPORTED.value]))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GroqClassificationAdapter(
        ClassifierConfig(api_key=None),
        client=client,
    )
    try:
        with pytest.raises(ClassifierProviderError) as caught:
            await adapter.classify("hello")
    finally:
        await client.aclose()

    assert caught.value.code is ProviderErrorCode.MISSING_API_KEY
    assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected", "retries"),
    [
        (401, ProviderErrorCode.AUTHENTICATION, 0),
        (403, ProviderErrorCode.AUTHENTICATION, 0),
        (404, ProviderErrorCode.MODEL_NOT_FOUND, 0),
        (400, ProviderErrorCode.REQUEST_REJECTED, 0),
    ],
)
async def test_nonretryable_http_errors_fail_without_retry(
    status: int,
    expected: ProviderErrorCode,
    retries: int,
) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, json={"error": "SECRET_PROVIDER_BODY"})

    adapter = _adapter(handler, max_retries=1)
    try:
        with pytest.raises(ClassifierProviderError) as caught:
            await adapter.classify("unclear")
    finally:
        await adapter._client.aclose()

    assert caught.value.code is expected
    assert calls == retries + 1
    assert "SECRET_PROVIDER_BODY" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, ProviderErrorCode.RATE_LIMITED),
        (500, ProviderErrorCode.PROVIDER_UNAVAILABLE),
        (503, ProviderErrorCode.PROVIDER_UNAVAILABLE),
    ],
)
async def test_transient_http_errors_retry_once_then_fail(
    status: int,
    expected: ProviderErrorCode,
) -> None:
    calls = 0
    delays: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, headers={"Retry-After": "0"})

    adapter = _adapter(handler, sleep_calls=delays)
    try:
        with pytest.raises(ClassifierProviderError) as caught:
            await adapter.classify("unclear")
    finally:
        await adapter._client.aclose()

    assert caught.value.code is expected
    assert calls == 2
    assert delays == [0]


@pytest.mark.asyncio
async def test_429_retry_after_is_respected_within_deadline() -> None:
    calls = 0
    delays: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0.2"})
        return _provider_response(_payload([Intent.COMPLAINT.value]))

    adapter = _adapter(handler, sleep_calls=delays)
    try:
        result = await adapter.classify("I have a complaint.")
    finally:
        await adapter._client.aclose()

    assert result.intents == (Intent.COMPLAINT,)
    assert calls == 2
    assert delays == [0.2]


@pytest.mark.asyncio
async def test_retry_after_beyond_deadline_does_not_sleep_or_retry() -> None:
    calls = 0
    delays: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "9"})

    adapter = _adapter(handler, sleep_calls=delays)
    try:
        with pytest.raises(ClassifierProviderError) as caught:
            await adapter.classify("unclear")
    finally:
        await adapter._client.aclose()

    assert caught.value.code is ProviderErrorCode.RATE_LIMITED
    assert calls == 1
    assert delays == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (httpx.ReadTimeout("private timeout detail"), ProviderErrorCode.TIMEOUT),
        (httpx.ConnectError("private connection detail"), ProviderErrorCode.CONNECTION),
    ],
)
async def test_timeout_and_connection_failure_are_sanitized(
    exception: Exception,
    expected: ProviderErrorCode,
) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise exception

    adapter = _adapter(handler, max_retries=0)
    try:
        with pytest.raises(ClassifierProviderError) as caught:
            await adapter.classify("unclear")
    finally:
        await adapter._client.aclose()

    assert caught.value.code is expected
    assert "private" not in str(caught.value)
    assert calls == 1


@pytest.mark.asyncio
async def test_total_deadline_bounds_a_slow_provider_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.1)
        return _provider_response(_payload([Intent.UNSUPPORTED.value]))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GroqClassificationAdapter(
        ClassifierConfig(
            api_key="test-only-not-a-real-key",
            max_retries=0,
            total_deadline_seconds=0.01,
        ),
        client=client,
    )
    try:
        with pytest.raises(ClassifierProviderError) as caught:
            await adapter.classify("unclear")
    finally:
        await client.aclose()

    assert caught.value.code is ProviderErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_retry_budget_is_exactly_one_additional_attempt() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("unavailable")

    adapter = _adapter(handler, max_retries=1)
    try:
        with pytest.raises(ClassifierProviderError):
            await adapter.classify("unclear")
    finally:
        await adapter._client.aclose()

    assert calls == 2


@pytest.mark.asyncio
async def test_rules_fast_path_hours_and_no_provider_call() -> None:
    class NoCall:
        async def classify(self, text: str) -> ModelClassificationPayload:
            raise AssertionError("Groq should not be called")

    result = await RuleFirstIntentClassifier(NoCall()).classify(
        "Are you open Saturday?"
    )

    assert result.status is ClassificationStatus.CLASSIFIED
    assert result.intents == (Intent.FAQ_BUSINESS_HOURS,)
    assert result.source is ClassifierSource.RULES
    assert result.confidence is None


@pytest.mark.parametrize(
    ("text", "expected_intent"),
    [
        ("How much is a haircut?", Intent.FAQ_SERVICE_POLICY),
        (
            "Is a haircut appointment available Friday?",
            Intent.APPOINTMENT_AVAILABILITY,
        ),
        ("I want to speak to someone.", Intent.HUMAN_REQUEST),
        ("Please cancel my appointment.", Intent.APPOINTMENT_MODIFY),
        ("Book a haircut appointment.", Intent.APPOINTMENT_CREATE),
        ("Show my appointment history.", Intent.CUSTOMER_ACCOUNT_LOOKUP),
        ("I have a complaint about my visit.", Intent.COMPLAINT),
    ],
)
def test_rules_classify_supported_single_intents(
    text: str,
    expected_intent: Intent,
) -> None:
    result = classify_with_rules(text)

    assert result.status is ClassificationStatus.CLASSIFIED
    assert result.intents == (expected_intent,)
    assert result.source is ClassifierSource.RULES


@pytest.mark.parametrize(
    ("text", "expected_service_id"),
    [
        ("How much is a beard trim?", "beard-trim"),
        ("How much is a trim beard?", "beard-trim"),
        ("How much is a trim my beard?", "beard-trim"),
        ("How much is beard trimming?", "beard-trim"),
        ("How much is a haircut?", "haircut"),
        ("How much is haircut and beard trim?", "haircut-beard"),
    ],
)
def test_rules_recognize_canonical_and_normalized_service_phrases(
    text: str,
    expected_service_id: str,
) -> None:
    result = classify_with_rules(text)

    assert result.status is ClassificationStatus.CLASSIFIED
    assert result.intents == (Intent.FAQ_SERVICE_POLICY,)
    assert result.entities.service_id == expected_service_id


@pytest.mark.parametrize(
    "text",
    [
        "I want trim beard",
        "I want to trim my beard",
    ],
)
def test_rules_clarify_general_beard_service_interest_without_groq(
    text: str,
) -> None:
    result = classify_with_rules(text)

    assert result.status is ClassificationStatus.CLARIFICATION
    assert result.reason_code == "service_interest_needs_intent"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "I want trim beard",
        "I want to trim my beard",
    ],
)
async def test_beard_service_interest_uses_rule_clarification_without_groq(
    text: str,
) -> None:
    class NoCall:
        async def classify(self, text: str) -> ModelClassificationPayload:
            raise AssertionError("Recognized service interest should not call Groq")

    result = await RuleFirstIntentClassifier(NoCall()).classify(text)

    assert result.status is ClassificationStatus.CLARIFICATION
    assert result.source is ClassifierSource.NONE
    assert result.provider_error is None
    assert result.reason_code == "service_interest_needs_intent"


@pytest.mark.asyncio
async def test_groq_cannot_infer_booking_from_service_mention() -> None:
    class IncorrectBookingGroq:
        async def classify(self, text: str) -> ModelClassificationPayload:
            return ModelClassificationPayload.model_validate(
                _payload(
                    [Intent.APPOINTMENT_CREATE.value],
                    service_id="beard-trim",
                )
            )

    result = await RuleFirstIntentClassifier(IncorrectBookingGroq()).classify(
        "Beard trim?"
    )

    assert result.status is ClassificationStatus.CLARIFICATION
    assert result.source is ClassifierSource.GROQ
    assert result.provider_error is None
    assert result.reason_code == "service_interest_needs_intent"


@pytest.mark.parametrize(
    "text",
    [
        "Book a beard trim appointment.",
        "I want to book a beard trim.",
        "Schedule a beard trimming appointment.",
    ],
)
def test_rules_require_explicit_booking_request_and_recognize_beard_service(
    text: str,
) -> None:
    result = classify_with_rules(text)

    assert result.status is ClassificationStatus.CLASSIFIED
    assert result.intents == (Intent.APPOINTMENT_CREATE,)
    assert result.entities.service_id == "beard-trim"


def test_rule_classification_preserves_compound_hours_and_availability() -> None:
    result = classify_with_rules(
        "Are you open Saturday, and do you have a haircut appointment?"
    )

    assert result.status is ClassificationStatus.CLASSIFIED
    assert result.intents == (
        Intent.FAQ_BUSINESS_HOURS,
        Intent.APPOINTMENT_AVAILABILITY,
    )
    assert result.entities.service_id == "haircut"
    assert result.entities.requested_date == "saturday"


@pytest.mark.parametrize(
    "text",
    [
        "Are you open on Sunday? How much is one haircut?",
        "How much is one haircut? Are you open on Sunday?",
    ],
)
def test_rules_classify_compound_hours_and_service_information(text: str) -> None:
    result = classify_with_rules(text)

    assert result.status is ClassificationStatus.CLASSIFIED
    assert result.intents == (
        Intent.FAQ_BUSINESS_HOURS,
        Intent.FAQ_SERVICE_POLICY,
    )
    assert result.entities.service_id == "haircut"
    assert result.entities.requested_date == "sunday"


@pytest.mark.asyncio
async def test_clear_compound_faq_uses_rules_without_groq() -> None:
    class CountingUnavailableGroq:
        def __init__(self) -> None:
            self.calls = 0

        async def classify(self, text: str) -> ModelClassificationPayload:
            self.calls += 1
            raise ClassifierProviderError(ProviderErrorCode.TIMEOUT)

    groq = CountingUnavailableGroq()
    result = await RuleFirstIntentClassifier(groq).classify(
        "Are you open on Sunday? How much is one haircut?"
    )

    assert groq.calls == 0
    assert result.status is ClassificationStatus.CLASSIFIED
    assert result.source is ClassifierSource.RULES
    assert result.intents == (
        Intent.FAQ_BUSINESS_HOURS,
        Intent.FAQ_SERVICE_POLICY,
    )


@pytest.mark.asyncio
async def test_hours_and_availability_compound_keeps_single_groq_fallback() -> None:
    class CountingUnavailableGroq:
        def __init__(self) -> None:
            self.calls = 0

        async def classify(self, text: str) -> ModelClassificationPayload:
            self.calls += 1
            raise ClassifierProviderError(ProviderErrorCode.TIMEOUT)

    groq = CountingUnavailableGroq()
    result = await RuleFirstIntentClassifier(groq).classify(
        "Are you open Saturday, and do you have a haircut appointment?"
    )

    assert groq.calls == 1
    assert result.source is ClassifierSource.RULES
    assert result.intents == (
        Intent.FAQ_BUSINESS_HOURS,
        Intent.APPOINTMENT_AVAILABILITY,
    )


@pytest.mark.asyncio
async def test_slots_without_a_service_use_availability_rules_without_groq() -> None:
    class NoCall:
        async def classify(self, text: str) -> ModelClassificationPayload:
            raise AssertionError("Clear slot wording should not call Groq")

    result = await RuleFirstIntentClassifier(NoCall()).classify(
        "Which slots are open on Wednesday?"
    )

    assert result.status is ClassificationStatus.CLASSIFIED
    assert result.intents == (Intent.APPOINTMENT_AVAILABILITY,)
    assert result.entities.service_id is None
    assert result.entities.requested_date == "wednesday"
    assert result.source is ClassifierSource.RULES


def test_date_correction_requires_session_context() -> None:
    without_context = classify_with_rules("Sorry, I meant Saturday.")
    with_context = classify_with_rules(
        "Sorry, I meant Saturday.",
        has_pending_availability_context=True,
    )

    assert without_context.status is ClassificationStatus.CLARIFICATION
    assert with_context.status is ClassificationStatus.CLASSIFIED
    assert with_context.intents == (Intent.APPOINTMENT_DATE_CORRECTION,)
    assert with_context.entities.requested_date == "saturday"


def test_unknown_or_ambiguous_messages_clarify_without_guessing() -> None:
    assert classify_with_rules("Tell me something.").status is ClassificationStatus.CLARIFICATION
    assert classify_with_rules(
        "Do you have a hair coloring appointment Friday?"
    ).status is ClassificationStatus.CLARIFICATION
    assert classify_with_rules("Are you open Saturday or Sunday?").status is ClassificationStatus.CLARIFICATION


@pytest.mark.parametrize(
    "text",
    [
        "Is a haircut appointment available next Friday?",
        "Is a haircut appointment available 2026-99-99?",
    ],
)
def test_rules_do_not_guess_unresolved_or_invalid_dates(text: str) -> None:
    result = classify_with_rules(text)

    assert result.status is ClassificationStatus.CLARIFICATION
    assert result.entities.requested_date is None


def test_rules_accept_explicit_full_date() -> None:
    result = classify_with_rules(
        "Is a haircut appointment available 2026-10-30?"
    )

    assert result.status is ClassificationStatus.CLASSIFIED
    assert result.intents == (Intent.APPOINTMENT_AVAILABILITY,)
    assert result.entities.requested_date == "2026-10-30"


@pytest.mark.asyncio
async def test_rules_fallback_when_groq_fails_and_no_intent_is_supported() -> None:
    class FailedGroq:
        async def classify(self, text: str) -> ModelClassificationPayload:
            raise ClassifierProviderError(ProviderErrorCode.TIMEOUT)

    result = await RuleFirstIntentClassifier(FailedGroq()).classify(
        "Maybe you can help."
    )

    assert result.status is ClassificationStatus.CLARIFICATION
    assert result.source is ClassifierSource.NONE
    assert result.intents == ()
    assert result.provider_error is ProviderErrorCode.TIMEOUT
    assert "raw" not in result.model_dump()


@pytest.mark.asyncio
async def test_ambiguous_date_does_not_call_groq_or_guess() -> None:
    class NoCall:
        async def classify(self, text: str) -> ModelClassificationPayload:
            raise AssertionError("Ambiguous date must not be resolved by guessing")

    result = await RuleFirstIntentClassifier(NoCall()).classify(
        "Is a haircut appointment available next Friday?"
    )

    assert result.status is ClassificationStatus.CLARIFICATION
    assert result.entities.requested_date is None
    assert result.reason_code == "ambiguous_or_conflicting_date"


@pytest.mark.asyncio
async def test_rules_fallback_preserves_supported_compound_when_groq_fails() -> None:
    class FailedGroq:
        async def classify(self, text: str) -> ModelClassificationPayload:
            raise ClassifierProviderError(ProviderErrorCode.RATE_LIMITED)

    result = await RuleFirstIntentClassifier(FailedGroq()).classify(
        "Are you open Saturday, and do you have a haircut appointment?"
    )

    assert result.status is ClassificationStatus.CLASSIFIED
    assert result.source is ClassifierSource.RULES
    assert result.confidence is None
    assert result.intents == (
        Intent.FAQ_BUSINESS_HOURS,
        Intent.APPOINTMENT_AVAILABILITY,
    )


@pytest.mark.asyncio
async def test_groq_unsupported_result_becomes_clarification() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return _provider_response(_payload([Intent.UNSUPPORTED.value]))

    adapter = _adapter(handler)
    try:
        result = await RuleFirstIntentClassifier(adapter).classify(
            "Give me some advice."
        )
    finally:
        await adapter._client.aclose()

    assert result.status is ClassificationStatus.CLARIFICATION
    assert result.source is ClassifierSource.GROQ
    assert result.intents == ()


@pytest.mark.asyncio
async def test_no_action_execution_or_reasoning_fields_in_result() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return _provider_response(
            _payload([Intent.APPOINTMENT_CREATE.value]),
            reasoning="PRIVATE_REASONING",
        )

    adapter = _adapter(handler)
    try:
        result = await RuleFirstIntentClassifier(adapter).classify(
            "Book a haircut appointment."
        )
    finally:
        await adapter._client.aclose()

    data = result.model_dump()
    assert data["intents"] == (Intent.APPOINTMENT_CREATE,)
    assert "tool_calls" not in data
    assert "actions" not in data
    assert "reasoning" not in data
    assert "PRIVATE_REASONING" not in repr(data)
