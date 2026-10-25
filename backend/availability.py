from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from backend.database import utc_now
from backend.fixtures import (
    AvailabilitySlotFixture,
    SalonFixtureBundle,
    ServiceFixture,
    availability_for_date,
    load_demo_salon_fixture,
)
from backend.models import (
    AvailabilityConversationContext,
    ConversationSession,
    PendingAvailabilityDateContext,
    SessionStatus,
)
from backend.service_phrases import mentioned_service_ids


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
    "thur": "thursday",
    "thurs": "thursday",
    "fri": "friday",
    "sat": "saturday",
    "sun": "sunday",
}
_TOKEN = re.compile(r"[a-z0-9]+")
_ISO_DATE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
_AVAILABILITY_TERMS = {
    "appointment",
    "appointments",
    "available",
    "availability",
    "booking",
    "bookings",
    "slot",
    "slots",
}
_CORRECTION_TERMS = {"actually", "instead", "meant", "sorry"}
_SERVICE_STOPWORDS = {
    "a",
    "an",
    "about",
    "any",
    "appointment",
    "appointments",
    "are",
    "available",
    "availability",
    "at",
    "book",
    "booking",
    "bookings",
    "can",
    "could",
    "do",
    "for",
    "have",
    "hours",
    "i",
    "is",
    "which",
    "open",
    "closed",
    "it",
    "on",
    "we",
    "what",
    "when",
    "your",
    "please",
    "salon",
    "slot",
    "slots",
    "the",
    "there",
    "this",
    "to",
    "you",
}


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    NO_RECORDED_SLOTS = "no_recorded_slots"
    INVALID_SERVICE = "invalid_service"
    INVALID_DATE = "invalid_date"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"
    NEEDS_CONTEXT = "needs_context"
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_CLOSED = "session_closed"


class AvailabilitySlot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_id: str = Field(min_length=1)
    service_id: str = Field(min_length=1)
    starts_at: datetime
    ends_at: datetime
    capacity: int = Field(gt=0)


class AvailabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AvailabilityStatus
    reason: str
    service_id: str | None = None
    requested_date: date | None = None
    slots: tuple[AvailabilitySlot, ...] = ()
    source_reference: str | None = None
    session_id: UUID | None = None

    @model_validator(mode="after")
    def validate_slots(self) -> AvailabilityResult:
        if self.status is AvailabilityStatus.AVAILABLE and not self.slots:
            raise ValueError("available results must include recorded slots")
        if self.status is not AvailabilityStatus.AVAILABLE and self.slots:
            raise ValueError("only available results may include slots")
        return self


class AvailabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    status: AvailabilityStatus
    session_id: UUID
    service_id: str | None = None
    requested_date: date | None = None
    slot_ids: tuple[str, ...] = ()
    source_reference: str | None = None
    reason: str


class AvailabilityService:
    """Read only the approved fixture's recorded availability slots."""

    def __init__(self, fixture: SalonFixtureBundle | None = None) -> None:
        self.fixture = fixture or load_demo_salon_fixture()
        self._services = {
            service.service_id: service for service in self.fixture.services
        }

    def lookup(
        self,
        *,
        service_id: str,
        requested_date: date | str,
    ) -> AvailabilityResult:
        if isinstance(requested_date, str):
            parsed_query_date = _parse_message_date(requested_date, self.fixture)
            if parsed_query_date.status is AvailabilityStatus.AMBIGUOUS:
                return _result(
                    AvailabilityStatus.AMBIGUOUS,
                    parsed_query_date.reason,
                    service_id=service_id,
                )
            parsed_date = parsed_query_date.value
        else:
            parsed_date = _parse_requested_date(requested_date)
        if parsed_date is None:
            return _result(
                AvailabilityStatus.INVALID_DATE,
                "invalid_or_ambiguous_date",
                service_id=service_id,
            )

        service = self._services.get(service_id)
        if service is None or not service.active:
            return _result(
                AvailabilityStatus.INVALID_SERVICE,
                "unknown_or_inactive_service",
                service_id=service_id,
                requested_date=parsed_date,
            )

        slots = tuple(
            sorted(
                availability_for_date(
                    self.fixture,
                    service_id=service_id,
                    requested_date=parsed_date,
                ),
                key=lambda slot: (slot.starts_at.astimezone(UTC), slot.slot_id),
            )
        )
        if any(not _slot_matches_service(slot, service) for slot in slots):
            return _result(
                AvailabilityStatus.UNSUPPORTED,
                "recorded_slot_duration_mismatch",
                service_id=service_id,
                requested_date=parsed_date,
            )
        if not slots:
            return _result(
                AvailabilityStatus.NO_RECORDED_SLOTS,
                "no_recorded_slots_for_service_and_date",
                service_id=service_id,
                requested_date=parsed_date,
            )
        return AvailabilityResult(
            status=AvailabilityStatus.AVAILABLE,
            reason="recorded_fixture_slots",
            service_id=service_id,
            requested_date=parsed_date,
            slots=tuple(_slot_model(slot) for slot in slots),
            source_reference="fixtures/demo_salon.json#/availability_slots",
        )


class AvailabilityConversationService:
    """Resolve scoped availability requests and persist only their selection context."""

    def __init__(
        self,
        availability: AvailabilityService | None = None,
    ) -> None:
        self.availability = availability or AvailabilityService()

    def respond(
        self,
        db: Session,
        *,
        session_id: UUID,
        message: str,
    ) -> AvailabilityResponse:
        session_key = str(session_id)
        conversation = db.get(ConversationSession, session_key)
        if conversation is None:
            return _response(
                AvailabilityStatus.SESSION_NOT_FOUND,
                "session_not_found",
                session_id=session_id,
            )
        if conversation.status != SessionStatus.ACTIVE.value:
            return _response(
                AvailabilityStatus.SESSION_CLOSED,
                "session_closed",
                session_id=session_id,
            )

        parsed_date = _parse_message_date(message, self.availability.fixture)
        if parsed_date.status is AvailabilityStatus.INVALID_DATE:
            return _response(
                AvailabilityStatus.INVALID_DATE,
                parsed_date.reason,
                session_id=session_id,
            )
        if parsed_date.status is AvailabilityStatus.AMBIGUOUS:
            return _response(
                AvailabilityStatus.AMBIGUOUS,
                parsed_date.reason,
                session_id=session_id,
            )

        has_availability_intent = _has_availability_intent(message)
        is_correction = _has_correction_intent(message)
        service_result = _match_service(
            message,
            self.availability.fixture.services,
        )
        if service_result.ambiguous:
            return _response(
                AvailabilityStatus.AMBIGUOUS,
                "multiple_services_in_request",
                session_id=session_id,
            )

        context = db.get(AvailabilityConversationContext, session_key)
        pending_date_context = db.get(PendingAvailabilityDateContext, session_key)
        if (
            not has_availability_intent
            and not is_correction
            and not (
                pending_date_context is not None
                and service_result.service_id is not None
            )
        ):
            return _response(
                AvailabilityStatus.UNSUPPORTED,
                "not_an_availability_request",
                session_id=session_id,
            )

        service_id = service_result.service_id
        if service_result.mentions_unknown:
            return _response(
                AvailabilityStatus.INVALID_SERVICE,
                "unknown_service",
                session_id=session_id,
                requested_date=parsed_date.value,
            )
        if service_id is None and context is not None:
            service_id = context.service_id

        requested_date = parsed_date.value
        if (
            requested_date is None
            and service_result.service_id is not None
            and pending_date_context is not None
        ):
            requested_date = pending_date_context.requested_date

        if requested_date is None:
            if is_correction:
                return _response(
                    AvailabilityStatus.NEEDS_CONTEXT,
                    "correction_requires_a_date",
                    session_id=session_id,
                    service_id=service_id,
                )
            return _response(
                AvailabilityStatus.NEEDS_CONTEXT,
                "request_requires_a_date",
                session_id=session_id,
                service_id=service_id,
                text="Please tell me one service and one clear date so I can check the recorded fixture.",
            )
        if service_id is None:
            if (
                context is None
                and is_correction
                and service_result.service_id is None
            ):
                return _response(
                    AvailabilityStatus.NEEDS_CONTEXT,
                    "correction_has_no_prior_service",
                    session_id=session_id,
                    requested_date=parsed_date.value,
                )
            if parsed_date.value is not None:
                _save_pending_date_context(
                    db,
                    session_id=session_key,
                    requested_date=parsed_date.value,
                )
            return _response(
                AvailabilityStatus.NEEDS_CONTEXT,
                "request_requires_a_service",
                session_id=session_id,
                requested_date=requested_date,
                text=(
                    f"Which service would you like to check for "
                    f"{parsed_date.value.isoformat()}? Please tell me one "
                    "service and one clear date so I can check the recorded fixture."
                    if parsed_date.value is not None
                    else None
                ),
            )

        result = self.availability.lookup(
            service_id=service_id,
            requested_date=requested_date,
        )
        if result.status in {
            AvailabilityStatus.AVAILABLE,
            AvailabilityStatus.NO_RECORDED_SLOTS,
        }:
            _save_context(
                db,
                session_id=session_key,
                service_id=service_id,
                requested_date=requested_date,
            )
            if pending_date_context is not None:
                db.delete(pending_date_context)
                db.commit()
        return _response_from_result(result, session_id)


class _ParsedDate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal[
        AvailabilityStatus.AVAILABLE,
        AvailabilityStatus.AMBIGUOUS,
        AvailabilityStatus.INVALID_DATE,
    ]
    reason: str
    value: date | None = None


class _MatchedService(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    service_id: str | None = None
    ambiguous: bool = False
    mentions_unknown: bool = False


def _parse_requested_date(value: date | str) -> date | None:
    if isinstance(value, datetime):
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_message_date(
    message: str,
    fixture: SalonFixtureBundle,
) -> _ParsedDate:
    iso_matches = _ISO_DATE.findall(message)
    tokens = _tokens(message)
    weekdays = {
        full_day
        for alias, full_day in _DAY_ALIASES.items()
        if alias in tokens
    }
    weekdays.update(day for day in _WEEKDAYS if day in tokens)
    relative: set[date] = set()
    pinned_date = fixture.pinned_clock.astimezone(UTC).date()
    if "today" in tokens:
        relative.add(pinned_date)
    if "tomorrow" in tokens:
        relative.add(pinned_date + timedelta(days=1))

    explicit_dates: set[date] = set()
    for raw_date in iso_matches:
        parsed = _parse_requested_date(raw_date)
        if parsed is None:
            return _ParsedDate(
                status=AvailabilityStatus.INVALID_DATE,
                reason="invalid_iso_date",
            )
        explicit_dates.add(parsed)
    if len(explicit_dates) > 1:
        return _ParsedDate(
            status=AvailabilityStatus.AMBIGUOUS,
            reason="multiple_explicit_dates",
        )
    if explicit_dates:
        explicit_date = next(iter(explicit_dates))
        conflicting_weekday = any(
            _WEEKDAYS[explicit_date.weekday()] != weekday
            for weekday in weekdays
        )
        if conflicting_weekday or relative:
            return _ParsedDate(
                status=AvailabilityStatus.AMBIGUOUS,
                reason="conflicting_explicit_and_relative_dates",
            )
        return _ParsedDate(
            status=AvailabilityStatus.AVAILABLE,
            reason="explicit_date",
            value=explicit_date,
        )
    if len(weekdays) > 1 or (weekdays and relative) or len(relative) > 1:
        return _ParsedDate(
            status=AvailabilityStatus.AMBIGUOUS,
            reason="multiple_or_conflicting_dates",
        )
    if weekdays:
        weekday = _WEEKDAYS.index(next(iter(weekdays)))
        days_until = (weekday - pinned_date.weekday()) % 7
        return _ParsedDate(
            status=AvailabilityStatus.AVAILABLE,
            reason="weekday_from_pinned_clock",
            value=pinned_date + timedelta(days=days_until),
        )
    if relative:
        return _ParsedDate(
            status=AvailabilityStatus.AVAILABLE,
            reason="relative_date_from_pinned_clock",
            value=next(iter(relative)),
        )
    return _ParsedDate(
        status=AvailabilityStatus.AVAILABLE,
        reason="date_not_provided",
    )


def _match_service(
    message: str,
    services: tuple[ServiceFixture, ...],
) -> _MatchedService:
    matched_ids = set(mentioned_service_ids(message, services))
    if len(matched_ids) > 1:
        return _MatchedService(ambiguous=True)
    if matched_ids:
        return _MatchedService(service_id=next(iter(matched_ids)))

    candidate_tokens = set(_TOKEN.findall(_ISO_DATE.sub(" ", message).casefold()))
    candidate_tokens.difference_update(_SERVICE_STOPWORDS)
    candidate_tokens.difference_update(_AVAILABILITY_TERMS)
    candidate_tokens.difference_update(_CORRECTION_TERMS)
    candidate_tokens.difference_update(_DAY_ALIASES)
    candidate_tokens.difference_update(_WEEKDAYS)
    candidate_tokens.difference_update(
        {"today", "tomorrow", "on", "friday", "saturday", "sunday"}
    )
    candidate_tokens.difference_update(_ISO_DATE.findall(message))
    return _MatchedService(mentions_unknown=bool(candidate_tokens))


def _slot_matches_service(
    slot: AvailabilitySlotFixture,
    service: ServiceFixture,
) -> bool:
    duration = slot.ends_at.astimezone(UTC) - slot.starts_at.astimezone(UTC)
    return duration == timedelta(minutes=service.duration_minutes)


def _slot_model(slot: AvailabilitySlotFixture) -> AvailabilitySlot:
    return AvailabilitySlot(
        slot_id=slot.slot_id,
        service_id=slot.service_id,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        capacity=slot.capacity,
    )


def _save_context(
    db: Session,
    *,
    session_id: str,
    service_id: str,
    requested_date: date,
) -> None:
    context = db.get(AvailabilityConversationContext, session_id)
    if context is None:
        context = AvailabilityConversationContext(
            session_id=session_id,
            service_id=service_id,
            requested_date=requested_date,
            updated_at=utc_now(),
        )
        db.add(context)
    else:
        context.service_id = service_id
        context.requested_date = requested_date
        context.updated_at = utc_now()
    db.commit()


def _save_pending_date_context(
    db: Session,
    *,
    session_id: str,
    requested_date: date,
) -> None:
    context = db.get(PendingAvailabilityDateContext, session_id)
    if context is None:
        context = PendingAvailabilityDateContext(
            session_id=session_id,
            requested_date=requested_date,
            updated_at=utc_now(),
        )
        db.add(context)
    else:
        context.requested_date = requested_date
        context.updated_at = utc_now()
    db.commit()


def _response_from_result(
    result: AvailabilityResult,
    session_id: UUID,
) -> AvailabilityResponse:
    if result.status is AvailabilityStatus.AVAILABLE:
        times = ", ".join(
            slot.starts_at.astimezone(UTC).strftime("%H:%M Etc/UTC")
            for slot in result.slots
        )
        text = (
            f"Recorded fixture availability for {result.service_id} on "
            f"{result.requested_date.isoformat()}: {times}. This is not a live "
            "calendar check and does not book an appointment."
        )
    elif result.status is AvailabilityStatus.NO_RECORDED_SLOTS:
        text = (
            f"I found no recorded fixture slots for {result.service_id} on "
            f"{result.requested_date.isoformat()}. This does not confirm real-world "
            "unavailability."
        )
    elif result.status is AvailabilityStatus.INVALID_SERVICE:
        text = "I can't check that service because it is unknown or inactive in the fixture."
    elif result.status is AvailabilityStatus.INVALID_DATE:
        text = "I couldn't interpret that date. Please provide one clear date."
    else:
        text = "I couldn't safely verify availability for that request."
    return _response(
        result.status,
        result.reason,
        session_id=session_id,
        service_id=result.service_id,
        requested_date=result.requested_date,
        slot_ids=tuple(slot.slot_id for slot in result.slots),
        source_reference=result.source_reference,
        text=text,
    )


def _response(
    status: AvailabilityStatus,
    reason: str,
    *,
    session_id: UUID,
    service_id: str | None = None,
    requested_date: date | None = None,
    slot_ids: tuple[str, ...] = (),
    source_reference: str | None = None,
    text: str | None = None,
) -> AvailabilityResponse:
    if text is None:
        text_by_status = {
            AvailabilityStatus.AMBIGUOUS: "I couldn't tell which date or service you meant. Please clarify.",
            AvailabilityStatus.NEEDS_CONTEXT: "Please specify one service and one date so I can check the recorded fixture.",
            AvailabilityStatus.INVALID_SERVICE: "I can't confirm availability for that service.",
            AvailabilityStatus.INVALID_DATE: "I couldn't interpret that date. Please provide one clear date.",
            AvailabilityStatus.UNSUPPORTED: "I can't check availability from that request.",
            AvailabilityStatus.SESSION_NOT_FOUND: "I couldn't find that conversation session.",
            AvailabilityStatus.SESSION_CLOSED: "This conversation is closed, so I can't update its availability context.",
            AvailabilityStatus.NO_RECORDED_SLOTS: "No recorded fixture slots were found.",
            AvailabilityStatus.AVAILABLE: "Recorded fixture slots were found.",
        }
        text = text_by_status[status]
    return AvailabilityResponse(
        text=text,
        status=status,
        session_id=session_id,
        service_id=service_id,
        requested_date=requested_date,
        slot_ids=slot_ids,
        source_reference=source_reference,
        reason=reason,
    )


def _result(
    status: AvailabilityStatus,
    reason: str,
    *,
    service_id: str | None = None,
    requested_date: date | None = None,
) -> AvailabilityResult:
    return AvailabilityResult(
        status=status,
        reason=reason,
        service_id=service_id,
        requested_date=requested_date,
    )


def _has_availability_intent(message: str) -> bool:
    tokens = set(_tokens(message))
    return bool(tokens & _AVAILABILITY_TERMS)


def _has_correction_intent(message: str) -> bool:
    tokens = set(_tokens(message))
    return bool(tokens & _CORRECTION_TERMS)


def _tokens(value: str) -> set[str]:
    return set(_ordered_tokens(value))


def _ordered_tokens(value: str) -> list[str]:
    return _TOKEN.findall(value.casefold())
