from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol, runtime_checkable

from backend.channels import CustomerRequest
from backend.fixtures import load_demo_salon_fixture
from backend.intent import Intent
from backend.knowledge import KnowledgeAnswer, KnowledgeService
from backend.rag import RagRetriever
from backend.service_phrases import mentioned_service_ids

_TOKEN = re.compile(r"[a-z0-9]+")
_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_DAY_ALIASES = {
    "mon": "monday",
    "tue": "tuesday",
    "tues": "tuesday",
    "wed": "wednesday",
    "thu": "thursday",
    "thurs": "thursday",
    "fri": "friday",
    "sat": "saturday",
    "sun": "sunday",
}


class Complexity(StrEnum):
    SIMPLE = "simple"
    COMPLEX = "complex"


@dataclass(frozen=True)
class ComplexityAssessment:
    """Outcome of complexity assessment for a customer request."""

    complexity: Complexity
    reason: str
    agent: str | None  # Agent name to route to, or None for simple path


@runtime_checkable
class AgentHandler(Protocol):
    """Protocol for specialized agent handlers.

    Each handler wraps existing domain capabilities and returns a
    CapabilityResult-compatible dict. Agents are deterministic wrappers,
    not autonomous LLM loops.
    """

    def handle(self, request: CustomerRequest) -> dict:
        ...


class AgentRegistry:
    """Registry mapping intent types to specialized agent handlers.

    Only intents that benefit from multi-step reasoning are registered.
    Simple single-intent queries continue through the deterministic
    LangGraph fast path.
    """

    def __init__(self) -> None:
        self._handlers: dict[Intent, AgentHandler] = {}

    def register(self, intent: Intent, handler: AgentHandler) -> None:
        self._handlers[intent] = handler

    def get(self, intent: Intent) -> AgentHandler | None:
        return self._handlers.get(intent)

    def registered_intents(self) -> tuple[Intent, ...]:
        return tuple(self._handlers.keys())


class ComplexityClassifier:
    """Rules-based complexity classifier.

    Determines whether a request can be handled by the deterministic
    fast path (simple) or requires a specialized agent (complex).
    No LLM is used; decisions are based on intent structure and
    message characteristics.
    """

    # Intents that are always simple (single deterministic capability).
    SIMPLE_INTENTS = frozenset(
        {
            Intent.FAQ_BUSINESS_HOURS,
            Intent.FAQ_SERVICE_POLICY,
            Intent.APPOINTMENT_AVAILABILITY,
            Intent.APPOINTMENT_DATE_CORRECTION,
            Intent.HUMAN_REQUEST,
            Intent.COMPLAINT,
        }
    )

    # Intents that may require multi-step reasoning (complex).
    COMPLEX_INTENTS = frozenset(
        {
            Intent.APPOINTMENT_CREATE,
            Intent.APPOINTMENT_MODIFY,
        }
    )

    def classify(
        self,
        request: CustomerRequest,
        intents: tuple[Intent, ...],
    ) -> ComplexityAssessment:
        """Classify request complexity based on intent structure and text."""

        # Unsupported -> clarification (no agent).
        if len(intents) == 1 and intents[0] == Intent.UNSUPPORTED:
            return ComplexityAssessment(
                complexity=Complexity.SIMPLE,
                reason="unsupported_intent",
                agent=None,
            )

        # Multiple intents -> complex (coordination needed, no dedicated agent).
        if len(intents) > 1:
            return ComplexityAssessment(
                complexity=Complexity.COMPLEX,
                reason="multiple_intents",
                agent=None,  # Handled by multi_intent_capability node
            )

        single_intent = intents[0]

        # Single complex intent -> specialized agent.
        if single_intent in self.COMPLEX_INTENTS:
            return ComplexityAssessment(
                complexity=Complexity.COMPLEX,
                reason="complex_single_intent",
                agent=single_intent.value,
            )

        # Single simple-intent FAQ/availability with multiple entities ->
        # complex: the deterministic single-lookup path cannot resolve
        # multiple services or dates in one call, so an agent coordinates
        # multiple lookups and combines the results.
        if single_intent in {
            Intent.FAQ_BUSINESS_HOURS,
            Intent.FAQ_SERVICE_POLICY,
        }:
            if self._requires_multi_entity_faq(request, single_intent):
                return ComplexityAssessment(
                    complexity=Complexity.COMPLEX,
                    reason="multi_entity_faq",
                    agent="faq",
                )

        if single_intent is Intent.APPOINTMENT_AVAILABILITY:
            if self._requires_multi_date_availability(request):
                return ComplexityAssessment(
                    complexity=Complexity.COMPLEX,
                    reason="multi_date_availability",
                    agent="availability",
                )

        # Single simple intent -> simple path.
        if single_intent in self.SIMPLE_INTENTS:
            return ComplexityAssessment(
                complexity=Complexity.SIMPLE,
                reason="single_simple_intent",
                agent=None,
            )

        # Fallback: simple path for anything unrecognized.
        return ComplexityAssessment(
            complexity=Complexity.SIMPLE,
            reason="unknown_intent",
            agent=None,
        )

    @staticmethod
    def _mentioned_services(request: CustomerRequest) -> tuple[str, ...]:
        return mentioned_service_ids(
            request.message_text, load_demo_salon_fixture().services
        )

    @staticmethod
    def _mentioned_days(text: str) -> tuple[str, ...]:
        tokens = set(_TOKEN.findall(text.casefold()))
        days: set[str] = set()
        for alias, full_day in _DAY_ALIASES.items():
            if alias in tokens:
                days.add(full_day)
        days.update(day for day in _WEEKDAYS if day in tokens)
        if "today" in tokens:
            days.add("today")
        if "tomorrow" in tokens:
            days.add("tomorrow")
        return tuple(sorted(days))

    @classmethod
    def _requires_multi_entity_faq(
        cls, request: CustomerRequest, intent: Intent
    ) -> bool:
        if intent is Intent.FAQ_SERVICE_POLICY:
            return len(cls._mentioned_services(request)) > 1
        if intent is Intent.FAQ_BUSINESS_HOURS:
            return len(cls._mentioned_days(request.message_text)) > 1
        return False

    @classmethod
    def _requires_multi_date_availability(
        cls, request: CustomerRequest
    ) -> bool:
        return len(cls._mentioned_days(request.message_text)) > 1


class FaqAgent:
    """FAQ agent: wraps the knowledge/RAG retriever for FAQ queries.

    Reuses existing A01-A05 retrieval capabilities. No LLM generation;
    all answers come from approved knowledge chunks.

    For complex FAQ tasks involving multiple services or days, the agent
    performs multiple lookups and combines the grounded results, preserving
    source IDs and retrieval reasons. It abstains from unsupported claims.
    """

    def __init__(self, knowledge: KnowledgeService, retriever: RagRetriever) -> None:
        self._knowledge = knowledge
        self._retriever = retriever

    def _lookup(self, text: str) -> KnowledgeAnswer:
        # Try semantic retrieval first, fall back to lexical, then OKF.
        answer = self._retriever.answer(text)
        if answer.status.value == "answered":
            return answer
        return self._knowledge.answer(text)

    def handle(self, request: CustomerRequest) -> dict:
        text = request.message_text
        service_ids = mentioned_service_ids(
            text, load_demo_salon_fixture().services
        )

        # Multi-service FAQ: look up each service and combine.
        if len(service_ids) > 1:
            results: list[KnowledgeAnswer] = []
            for service_id in service_ids:
                service = next(
                    (
                        s
                        for s in load_demo_salon_fixture().services
                        if s.service_id == service_id
                    ),
                    None,
                )
                if service is None:
                    continue
                query = f"What is the price and duration of {service.name}?"
                # Use OKF directly for individual service lookups so the
                # retriever cannot conflate the combined service with
                # individual service facts.
                answer = self._knowledge.answer(query)
                results.append(answer)

            if not results:
                return {
                    "intent": Intent.FAQ_SERVICE_POLICY,
                    "text": "I don't have approved details for those services.",
                    "source_ids": (),
                    "outcome": "unsupported",
                    "retrieval_reason": "",
                }

            parts: list[str] = []
            all_source_ids: list[str] = []
            all_unsupported = True
            for answer in results:
                if answer.status.value == "answered":
                    all_unsupported = False
                    parts.append(answer.text)
                    all_source_ids.extend(answer.source_ids)
                else:
                    parts.append(answer.text)

            combined = " ".join(parts)
            if all_unsupported:
                outcome = "unsupported"
            else:
                outcome = "answered"

            return {
                "intent": Intent.FAQ_SERVICE_POLICY,
                "text": combined,
                "source_ids": tuple(dict.fromkeys(all_source_ids)),
                "outcome": outcome,
                "retrieval_reason": tuple(
                    dict.fromkeys(
                        r.reason for r in results if r.reason
                    )
                ),
            }

        # Single-service FAQ (existing behavior).
        answer = self._lookup(text)
        if answer.status.value == "answered":
            return {
                "intent": Intent.FAQ_BUSINESS_HOURS,
                "text": answer.text,
                "source_ids": answer.source_ids,
                "outcome": "answered",
                "retrieval_reason": answer.reason,
            }
        # Fall back to deterministic OKF path.
        okf_answer = self._knowledge.answer(text)
        return {
            "intent": Intent.FAQ_BUSINESS_HOURS,
            "text": okf_answer.text,
            "source_ids": okf_answer.source_ids,
            "outcome": (
                "answered"
                if okf_answer.status.value == "answered"
                else "unsupported"
            ),
            "retrieval_reason": okf_answer.reason,
        }


class AvailabilityAgent:
    """Availability agent: wraps the read-only availability service.

    Reuses existing P0 availability capability. No booking writes.

    For complex availability tasks involving multiple dates, the agent
    splits the request into per-date lookups through the existing
    availability service and combines the grounded results, preserving
    session context and disclosing that availability is recorded demo data.
    """

    def __init__(self, availability_service) -> None:
        self._availability = availability_service

    def _mentioned_days(self, text: str) -> tuple[str, ...]:
        tokens = set(_TOKEN.findall(text.casefold()))
        days: set[str] = set()
        for alias, full_day in _DAY_ALIASES.items():
            if alias in tokens:
                days.add(full_day)
        days.update(day for day in _WEEKDAYS if day in tokens)
        if "today" in tokens:
            days.add("today")
        if "tomorrow" in tokens:
            days.add("tomorrow")
        return tuple(sorted(days))

    def handle(
        self, request: CustomerRequest, db, session_id
    ) -> dict:
        from backend.availability import AvailabilityConversationService

        # Single-date request: delegate directly to the existing service.
        response = self._availability.respond(
            db, session_id=session_id, message=request.message_text
        )

        # Multi-date request: the existing service returns AMBIGUOUS for
        # multiple dates. Split into per-date lookups and combine results.
        if response.status is not None and (
            response.status.value == "ambiguous"
            and len(self._mentioned_days(request.message_text)) > 1
        ):
            return self._handle_multi_date(
                request, db, session_id, response
            )

        return {
            "intent": Intent.APPOINTMENT_AVAILABILITY,
            "text": response.text,
            "source_ids": tuple(
                source
                for source in (response.source_reference, *response.slot_ids)
                if source is not None
            ),
            "outcome": response.status.value,
            "retrieval_reason": response.reason,
        }

    def _handle_multi_date(
        self,
        request: CustomerRequest,
        db,
        session_id: str,
        first_response,
    ) -> dict:
        from backend.fixtures import load_demo_salon_fixture
        from backend.service_phrases import mentioned_service_ids

        service_ids = mentioned_service_ids(
            request.message_text, load_demo_salon_fixture().services
        )
        service_id = service_ids[0] if service_ids else None

        days = self._mentioned_days(request.message_text)
        if not days:
            return {
                "intent": Intent.APPOINTMENT_AVAILABILITY,
                "text": first_response.text,
                "source_ids": tuple(
                    source
                    for source in (first_response.source_reference, *first_response.slot_ids)
                    if source is not None
                ),
                "outcome": first_response.status.value,
                "retrieval_reason": first_response.reason,
            }

        parts: list[str] = []
        all_source_ids: list[str] = []
        has_available = False
        has_unavailable = False

        for day in days:
            date_str = day
            if service_id is not None:
                message = f"Do you have a {service_id} appointment on {date_str}?"
            else:
                message = f"Do you have an appointment on {date_str}?"

            day_response = self._availability.respond(
                db, session_id=session_id, message=message
            )
            status = day_response.status.value
            if status in {"available", "no_recorded_slots"}:
                if status == "available":
                    has_available = True
                else:
                    has_unavailable = True
                parts.append(day_response.text)
            else:
                parts.append(day_response.text)
                if status in {"invalid_service", "invalid_date"}:
                    has_unavailable = True
            all_source_ids.extend(
                source
                for source in (day_response.source_reference, *day_response.slot_ids)
                if source is not None
            )

        combined = " ".join(parts)
        if has_available:
            outcome = "answered"
        elif has_unavailable:
            outcome = "unsupported"
        else:
            outcome = "clarification"

        return {
            "intent": Intent.APPOINTMENT_AVAILABILITY,
            "text": combined,
            "source_ids": tuple(dict.fromkeys(all_source_ids)),
            "outcome": outcome,
            "retrieval_reason": tuple(
                dict.fromkeys(r.reason for r in [first_response] if r.reason)
            ),
        }


class SupportAgent:
    """Support agent: wraps the handoff/ticket system.

    Reuses existing P0 handoff capabilities. No ticket creation without
    explicit confirmation.
    """

    def __init__(
        self,
        create_handoff_ticket,
        knowledge: KnowledgeService | None = None,
    ) -> None:
        self._create_handoff_ticket = create_handoff_ticket
        self._knowledge = knowledge or KnowledgeService()

    def handle(
        self,
        request: CustomerRequest,
        db,
        session_id,
        trace_id,
        intent: Intent | None = None,
    ) -> dict:
        # Support agent does NOT create tickets directly. It evaluates
        # whether a handoff is warranted and returns guidance. Actual
        # ticket creation happens only through the pending-confirmation
        # flow in the workflow.
        # Booking intents have deterministic unsupported-booking messages.
        if intent is Intent.APPOINTMENT_CREATE:
            return {
                "intent": Intent.APPOINTMENT_CREATE,
                "text": "I can check the recorded slots, but I can't book an appointment in this demo.",
                "source_ids": (),
                "outcome": "handoff_unavailable",
                "retrieval_reason": "",
            }
        if intent is Intent.APPOINTMENT_MODIFY:
            return {
                "intent": Intent.APPOINTMENT_MODIFY,
                "text": "I can't access or change existing appointments in this demo. No booking was changed.",
                "source_ids": (),
                "outcome": "handoff_unavailable",
                "retrieval_reason": "",
            }
        text = request.message_text.lower()
        if any(
            word in text
            for word in ("human", "staff", "agent", "talk to someone", "speak to someone")
        ):
            return {
                "intent": Intent.HUMAN_REQUEST,
                "text": "Would you like me to create a queued support ticket for staff to follow up? Please reply yes or no.",
                "source_ids": (),
                "outcome": "handoff_unavailable",
                "retrieval_reason": "human_request_detected",
            }
        # Complaint: use deterministic OKF path for grounded response.
        answer = self._knowledge.answer(text)
        return {
            "intent": Intent.COMPLAINT,
            "text": (
                f"{answer.text} I can't create a support ticket or claim "
                "that a staff member has been notified in this demo."
            ),
            "source_ids": answer.source_ids,
            "outcome": "handoff_unavailable",
            "retrieval_reason": answer.reason,
        }
