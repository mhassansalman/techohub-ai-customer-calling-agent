from __future__ import annotations

from datetime import date
from typing import Literal, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from backend.availability import (
    AvailabilityConversationService,
    AvailabilityResponse,
    AvailabilityStatus,
)
from backend.channels import CustomerRequest
from backend.intent import (
    ClassificationStatus,
    ClassifierSource,
    Intent,
    IntentClassification,
    IntentClassifier,
    ProviderErrorCode,
)
from backend.knowledge import AnswerStatus, KnowledgeAnswer, KnowledgeService
from backend.models import (
    AvailabilityConversationContext,
    PendingAvailabilityDateContext,
)


class CapabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: Intent
    text: str = Field(min_length=1)
    source_ids: tuple[str, ...] = ()
    outcome: Literal["answered", "clarification", "handoff_unavailable", "unsupported"]


class ConversationWorkflowResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    response_text: str = Field(min_length=1)
    intents: tuple[Intent, ...] = ()
    classification_source: ClassifierSource
    source_ids: tuple[str, ...] = ()
    outcome: Literal["answered", "clarification", "handoff_unavailable", "unsupported"]


class WorkflowExecutionError(RuntimeError):
    """Sanitized boundary error for graph failures after the customer turn is saved."""


class ConversationState(TypedDict, total=False):
    session_id: UUID
    request: CustomerRequest
    db: Session
    has_pending_availability_context: bool
    classification: IntentClassification
    capability_results: tuple[CapabilityResult, ...]
    response: ConversationWorkflowResult


class ConversationWorkflow:
    """Small LangGraph router over the existing deterministic capabilities."""

    def __init__(
        self,
        *,
        classifier: IntentClassifier,
        knowledge: KnowledgeService | None = None,
        availability: AvailabilityConversationService | None = None,
    ) -> None:
        self.classifier = classifier
        self.knowledge = knowledge or KnowledgeService()
        self.availability = availability or AvailabilityConversationService()
        self.graph = self._build_graph()

    async def run(
        self,
        *,
        session_id: UUID,
        request: CustomerRequest,
        db: Session,
    ) -> ConversationWorkflowResult:
        try:
            context = db.get(AvailabilityConversationContext, str(session_id))
            pending_date = db.get(
                PendingAvailabilityDateContext,
                str(session_id),
            )
            has_pending_context = context is not None or pending_date is not None
            if db.in_transaction():
                db.rollback()

            state = await self.graph.ainvoke(
                {
                    "session_id": session_id,
                    "request": request,
                    "db": db,
                    "has_pending_availability_context": has_pending_context,
                }
            )
        except Exception as error:
            raise WorkflowExecutionError("conversation workflow failed") from error
        return ConversationWorkflowResult.model_validate(state["response"])

    def _build_graph(self):
        builder = StateGraph(ConversationState)
        builder.add_node("classify_intent", self._classify_intent)
        builder.add_node("faq_capability", self._faq_capability)
        builder.add_node("availability_capability", self._availability_capability)
        builder.add_node("date_correction", self._date_correction)
        builder.add_node("support_capability", self._support_capability)
        builder.add_node("multi_intent_capability", self._multi_intent_capability)
        builder.add_node("clarification", self._clarification)
        builder.add_node("aggregate_response", self._aggregate_response)

        builder.add_edge(START, "classify_intent")
        builder.add_conditional_edges(
            "classify_intent",
            self._route,
            {
                "faq": "faq_capability",
                "availability": "availability_capability",
                "date_correction": "date_correction",
                "support": "support_capability",
                "multi": "multi_intent_capability",
                "clarification": "clarification",
            },
        )
        for node in (
            "faq_capability",
            "availability_capability",
            "date_correction",
            "support_capability",
            "multi_intent_capability",
            "clarification",
        ):
            builder.add_edge(node, "aggregate_response")
        builder.add_edge("aggregate_response", END)
        return builder.compile()

    async def _classify_intent(
        self,
        state: ConversationState,
    ) -> dict[str, IntentClassification]:
        try:
            result = await self.classifier.classify(
                state["request"].message_text,
                has_pending_availability_context=state[
                    "has_pending_availability_context"
                ],
            )
            classification = IntentClassification.model_validate(result)
        except ValidationError:
            classification = IntentClassification(
                status=ClassificationStatus.CLARIFICATION,
                source=ClassifierSource.NONE,
                provider_error=ProviderErrorCode.INVALID_RESPONSE,
                reason_code="invalid_classifier_result",
            )
        return {"classification": classification}

    @staticmethod
    def _route(state: ConversationState) -> str:
        classification = state["classification"]
        if classification.status is not ClassificationStatus.CLASSIFIED:
            return "clarification"
        intents = classification.intents
        if not intents or Intent.UNSUPPORTED in intents:
            return "clarification"
        if len(intents) > 1:
            return "multi"
        intent = intents[0]
        if intent in {Intent.FAQ_BUSINESS_HOURS, Intent.FAQ_SERVICE_POLICY}:
            return "faq"
        if intent is Intent.APPOINTMENT_AVAILABILITY:
            return "availability"
        if intent is Intent.APPOINTMENT_DATE_CORRECTION:
            return "date_correction"
        if intent in _SUPPORT_INTENTS:
            return "support"
        return "clarification"

    def _faq_capability(
        self,
        state: ConversationState,
    ) -> dict[str, tuple[CapabilityResult, ...]]:
        classification = state["classification"]
        intent = classification.intents[0]
        answer = self.knowledge.answer(state["request"].message_text)
        return {
            "capability_results": (
                _knowledge_result(intent, answer),
            )
        }

    def _availability_capability(
        self,
        state: ConversationState,
    ) -> dict[str, tuple[CapabilityResult, ...]]:
        response = self.availability.respond(
            state["db"],
            session_id=state["session_id"],
            message=state["request"].message_text,
        )
        return {
            "capability_results": (
                _availability_result(Intent.APPOINTMENT_AVAILABILITY, response),
            )
        }

    def _date_correction(
        self,
        state: ConversationState,
    ) -> dict[str, tuple[CapabilityResult, ...]]:
        response = self.availability.respond(
            state["db"],
            session_id=state["session_id"],
            message=state["request"].message_text,
        )
        return {
            "capability_results": (
                _availability_result(Intent.APPOINTMENT_DATE_CORRECTION, response),
            )
        }

    def _support_capability(
        self,
        state: ConversationState,
    ) -> dict[str, tuple[CapabilityResult, ...]]:
        intent = state["classification"].intents[0]
        return {
            "capability_results": (
                _support_result(
                    intent,
                    state["request"].message_text,
                    self.knowledge,
                ),
            )
        }

    def _multi_intent_capability(
        self,
        state: ConversationState,
    ) -> dict[str, tuple[CapabilityResult, ...]]:
        classification = state["classification"]
        text = state["request"].message_text
        results: list[CapabilityResult] = []
        has_hours_and_compound_intent = Intent.FAQ_BUSINESS_HOURS in (
            classification.intents
        ) and bool(
            set(classification.intents)
            & {
                Intent.APPOINTMENT_AVAILABILITY,
                Intent.FAQ_SERVICE_POLICY,
            }
        )

        for intent in classification.intents:
            if intent is Intent.FAQ_BUSINESS_HOURS:
                query = (
                    _hours_query(classification.entities.requested_date)
                    if has_hours_and_compound_intent
                    else text
                )
                results.append(
                    _knowledge_result(intent, self.knowledge.answer(query))
                )
            elif intent is Intent.FAQ_SERVICE_POLICY:
                results.append(
                    _knowledge_result(
                        intent,
                        self.knowledge.answer(
                            _service_query(
                                classification.entities.service_id,
                                self.knowledge,
                                text,
                            )
                        ),
                    )
                )
            elif intent in {
                Intent.APPOINTMENT_AVAILABILITY,
                Intent.APPOINTMENT_DATE_CORRECTION,
            }:
                availability_response = self.availability.respond(
                    state["db"],
                    session_id=state["session_id"],
                    message=text,
                )
                results.append(_availability_result(intent, availability_response))
            elif intent in _SUPPORT_INTENTS:
                results.append(
                    _support_result(intent, text, self.knowledge)
                )
            else:
                results.append(
                    CapabilityResult(
                        intent=intent,
                        text="I couldn't safely handle every part of that request. "
                        "Please clarify what you need.",
                        outcome="clarification",
                    )
                )
        return {"capability_results": tuple(results)}

    @staticmethod
    def _clarification(
        state: ConversationState,
    ) -> dict[str, tuple[CapabilityResult, ...]]:
        classification = state["classification"]
        text = (
            "I couldn't safely understand that request. Please rephrase or "
            "ask one question at a time."
        )
        if classification.reason_code in {
            "availability_requires_service_and_date",
            "request_requires_a_service",
            "request_requires_a_date",
            "date_correction_without_context",
        }:
            text = (
                "Please tell me one service and one clear date so I can check "
                "recorded availability."
            )
        elif (
            classification.provider_error is not None
            and classification.reason_code != "invalid_classifier_result"
        ):
            text = (
                "I couldn't safely classify that request right now. Please "
                "rephrase it or try again later."
            )
        return {
            "capability_results": (
                CapabilityResult(
                    intent=Intent.UNSUPPORTED,
                    text=text,
                    outcome="clarification",
                ),
            )
        }

    @staticmethod
    def _aggregate_response(
        state: ConversationState,
    ) -> dict[str, ConversationWorkflowResult]:
        results = state.get("capability_results", ())
        if not results:
            results = (
                CapabilityResult(
                    intent=Intent.UNSUPPORTED,
                    text="I couldn't safely process that request. Please try again.",
                    outcome="clarification",
                ),
            )
        outcomes = {result.outcome for result in results}
        if "clarification" in outcomes:
            outcome = "clarification"
        elif "handoff_unavailable" in outcomes:
            outcome = "handoff_unavailable"
        elif "unsupported" in outcomes:
            outcome = "unsupported"
        else:
            outcome = "answered"
        classification = state["classification"]
        return {
            "response": ConversationWorkflowResult(
                response_text="\n\n".join(result.text for result in results),
                intents=classification.intents,
                classification_source=classification.source,
                source_ids=tuple(
                    dict.fromkeys(
                        source_id
                        for result in results
                        for source_id in result.source_ids
                    )
                ),
                outcome=outcome,
            )
        }


_SUPPORT_INTENTS = {
    Intent.APPOINTMENT_CREATE,
    Intent.APPOINTMENT_MODIFY,
    Intent.CUSTOMER_ACCOUNT_LOOKUP,
    Intent.COMPLAINT,
    Intent.HUMAN_REQUEST,
}


def _knowledge_result(
    intent: Intent,
    answer: KnowledgeAnswer,
) -> CapabilityResult:
    return CapabilityResult(
        intent=intent,
        text=answer.text,
        source_ids=answer.source_ids,
        outcome=(
            "answered"
            if answer.status is AnswerStatus.ANSWERED
            else "unsupported"
        ),
    )


def _support_result(
    intent: Intent,
    text: str,
    knowledge: KnowledgeService,
) -> CapabilityResult:
    if intent is Intent.COMPLAINT:
        answer = knowledge.answer(text)
        if answer.status is AnswerStatus.ANSWERED:
            return _knowledge_result(intent, answer)
        return CapabilityResult(
            intent=intent,
            text=(
                f"{answer.text} I can't create a support ticket or claim "
                "that a staff member has been notified in this demo."
            ),
            source_ids=answer.source_ids,
            outcome="handoff_unavailable",
        )

    messages = {
        Intent.HUMAN_REQUEST: (
            "I can't transfer this chat or notify a staff member from this "
            "demo. Please contact salon staff directly through a contact "
            "method you already have."
        ),
        Intent.APPOINTMENT_CREATE: (
            "I can check recorded fixture availability, but appointment "
            "booking is not available here. No appointment was created."
        ),
        Intent.APPOINTMENT_MODIFY: (
            "I can't access or change existing appointments in this demo. "
            "No booking was changed."
        ),
        Intent.CUSTOMER_ACCOUNT_LOOKUP: (
            "I can't access customer records in this demo. No personal "
            "account information was retrieved."
        ),
    }
    return CapabilityResult(
        intent=intent,
        text=messages[intent],
        outcome="handoff_unavailable",
    )


def _availability_result(
    intent: Intent,
    response: AvailabilityResponse,
) -> CapabilityResult:
    if response.status in {
        AvailabilityStatus.AVAILABLE,
        AvailabilityStatus.NO_RECORDED_SLOTS,
    }:
        outcome: Literal["answered", "clarification", "handoff_unavailable", "unsupported"] = (
            "answered"
        )
    elif response.status in {
        AvailabilityStatus.NEEDS_CONTEXT,
        AvailabilityStatus.AMBIGUOUS,
        AvailabilityStatus.INVALID_DATE,
    }:
        outcome = "clarification"
    else:
        outcome = "unsupported"
    source_ids = tuple(
        source
        for source in (response.source_reference, *response.slot_ids)
        if source is not None
    )
    return CapabilityResult(
        intent=intent,
        text=response.text,
        source_ids=source_ids,
        outcome=outcome,
    )


def _hours_query(requested_date: str | None) -> str:
    if not requested_date:
        return "What are your opening hours?"
    try:
        day = date.fromisoformat(requested_date).strftime("%A")
    except ValueError:
        day = requested_date
    return f"What are the opening hours on {day}?"


def _service_query(
    service_id: str | None,
    knowledge: KnowledgeService,
    fallback: str,
) -> str:
    if service_id is None:
        return fallback
    service = next(
        (
            service
            for service in knowledge.fixture.services
            if service.service_id == service_id
        ),
        None,
    )
    return f"What is the price and duration of {service.name}?" if service else fallback
