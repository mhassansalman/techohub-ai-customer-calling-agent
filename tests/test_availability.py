from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import inspect, select

from backend.availability import (
    AvailabilityConversationService,
    AvailabilityService,
    AvailabilityStatus,
)
from backend.database import Base, create_database_engine, create_session_factory
from backend.fixtures import (
    CANONICAL_FIXTURE_PATH,
    load_demo_salon_fixture,
)
from backend.models import (
    AvailabilityConversationContext,
    ConversationSession,
    SessionOutcome,
    SessionStatus,
)
from backend.session_service import close_session, start_session


@pytest.fixture
def availability() -> AvailabilityService:
    return AvailabilityService()


@pytest.fixture
def database(tmp_path: Path):
    database_path = tmp_path / "availability.sqlite3"
    url = f"sqlite:///{database_path.as_posix()}"
    engine = create_database_engine(url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    try:
        yield engine, factory, database_path, url
    finally:
        engine.dispose()


def _new_session(factory) -> UUID:
    with factory() as db:
        conversation = start_session(db, channel_type="text_web")
        return UUID(conversation.id)


def test_friday_haircut_availability_uses_canonical_slots(
    availability: AvailabilityService,
) -> None:
    result = availability.lookup(
        service_id="haircut",
        requested_date="2026-10-30",
    )

    assert result.status is AvailabilityStatus.AVAILABLE
    assert [slot.slot_id for slot in result.slots] == [
        "haircut-2026-10-30-1000",
        "haircut-2026-10-30-1400",
    ]
    assert [slot.starts_at.strftime("%H:%M") for slot in result.slots] == [
        "10:00",
        "14:00",
    ]
    assert result.source_reference == (
        "fixtures/demo_salon.json#/availability_slots"
    )


def test_saturday_haircut_availability_is_recorded(
    availability: AvailabilityService,
) -> None:
    result = availability.lookup(
        service_id="haircut",
        requested_date=date(2026, 10, 31),
    )

    assert result.status is AvailabilityStatus.AVAILABLE
    assert [slot.slot_id for slot in result.slots] == [
        "haircut-2026-10-31-1000"
    ]


def test_relative_weekday_uses_pinned_clock_in_direct_lookup(
    availability: AvailabilityService,
) -> None:
    result = availability.lookup(
        service_id="haircut",
        requested_date="Friday",
    )

    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.requested_date == date(2026, 10, 30)
    assert tuple(slot.slot_id for slot in result.slots) == (
        "haircut-2026-10-30-1000",
        "haircut-2026-10-30-1400",
    )


def test_ambiguous_relative_date_is_not_guessed(
    availability: AvailabilityService,
) -> None:
    result = availability.lookup(
        service_id="haircut",
        requested_date="Friday or Saturday",
    )

    assert result.status is AvailabilityStatus.AMBIGUOUS
    assert result.slots == ()


def test_sunday_reports_no_recorded_slots_not_real_world_unavailability(
    availability: AvailabilityService,
) -> None:
    result = availability.lookup(
        service_id="haircut",
        requested_date=date(2026, 11, 1),
    )

    assert result.status is AvailabilityStatus.NO_RECORDED_SLOTS
    assert result.slots == ()
    assert result.reason == "no_recorded_slots_for_service_and_date"


@pytest.mark.parametrize("service_id", ["unknown", "hair-color"])
def test_unknown_service_is_rejected(
    availability: AvailabilityService,
    service_id: str,
) -> None:
    result = availability.lookup(
        service_id=service_id,
        requested_date=date(2026, 10, 30),
    )

    assert result.status is AvailabilityStatus.INVALID_SERVICE
    assert result.slots == ()


def test_inactive_service_is_rejected() -> None:
    fixture = load_demo_salon_fixture()
    services = tuple(
        service.model_copy(update={"active": False})
        if service.service_id == "haircut"
        else service
        for service in fixture.services
    )
    inactive_fixture = fixture.model_copy(update={"services": services})

    result = AvailabilityService(inactive_fixture).lookup(
        service_id="haircut",
        requested_date=date(2026, 10, 30),
    )

    assert result.status is AvailabilityStatus.INVALID_SERVICE
    assert result.reason == "unknown_or_inactive_service"


@pytest.mark.parametrize(
    "requested_date",
    ["not-a-date", "2026-02-30", datetime(2026, 10, 30)],
)
def test_invalid_dates_are_not_coerced(
    availability: AvailabilityService,
    requested_date: str | datetime,
) -> None:
    result = availability.lookup(
        service_id="haircut",
        requested_date=requested_date,
    )

    assert result.status is AvailabilityStatus.INVALID_DATE
    assert result.slots == ()


def test_recorded_slots_are_sorted_deterministically() -> None:
    fixture = load_demo_salon_fixture()
    reversed_fixture = fixture.model_copy(
        update={"availability_slots": tuple(reversed(fixture.availability_slots))}
    )
    result = AvailabilityService(reversed_fixture).lookup(
        service_id="haircut",
        requested_date=date(2026, 10, 30),
    )

    assert [slot.starts_at.strftime("%H:%M") for slot in result.slots] == [
        "10:00",
        "14:00",
    ]


def test_incompatible_recorded_slot_duration_is_not_returned() -> None:
    fixture = load_demo_salon_fixture()
    first_slot = fixture.availability_slots[0].model_copy(
        update={"ends_at": fixture.availability_slots[0].ends_at + timedelta(minutes=5)}
    )
    inconsistent_fixture = fixture.model_copy(
        update={
            "availability_slots": (
                first_slot,
                *fixture.availability_slots[1:],
            )
        }
    )

    result = AvailabilityService(inconsistent_fixture).lookup(
        service_id="haircut",
        requested_date=date(2026, 10, 30),
    )

    assert result.status is AvailabilityStatus.UNSUPPORTED
    assert result.reason == "recorded_slot_duration_mismatch"
    assert result.slots == ()


def test_friday_to_saturday_correction_preserves_service_and_session(
    database,
) -> None:
    _, factory, _, _ = database
    session_id = _new_session(factory)
    conversation = AvailabilityConversationService()

    with factory() as db:
        friday = conversation.respond(
            db,
            session_id=session_id,
            message="Do you have a haircut appointment on Friday?",
        )
        saturday = conversation.respond(
            db,
            session_id=session_id,
            message="Sorry, I meant Saturday.",
        )

    assert friday.status is AvailabilityStatus.AVAILABLE
    assert friday.service_id == "haircut"
    assert friday.requested_date == date(2026, 10, 30)
    assert friday.slot_ids == (
        "haircut-2026-10-30-1000",
        "haircut-2026-10-30-1400",
    )
    assert saturday.status is AvailabilityStatus.AVAILABLE
    assert saturday.session_id == session_id
    assert saturday.service_id == friday.service_id == "haircut"
    assert saturday.requested_date == date(2026, 10, 31)
    assert saturday.slot_ids == ("haircut-2026-10-31-1000",)
    assert "does not book an appointment" in saturday.text


def test_context_is_isolated_between_sessions(database) -> None:
    _, factory, _, _ = database
    first_session = _new_session(factory)
    second_session = _new_session(factory)
    conversation = AvailabilityConversationService()

    with factory() as db:
        first = conversation.respond(
            db,
            session_id=first_session,
            message="Do you have a haircut appointment Friday?",
        )
        other_session_correction = conversation.respond(
            db,
            session_id=second_session,
            message="Sorry, I meant Saturday.",
        )

    assert first.status is AvailabilityStatus.AVAILABLE
    assert other_session_correction.status is AvailabilityStatus.NEEDS_CONTEXT
    assert other_session_correction.service_id is None
    with factory() as db:
        assert db.get(AvailabilityConversationContext, str(second_session)) is None


def test_correction_without_prior_service_is_safe(database) -> None:
    _, factory, _, _ = database
    session_id = _new_session(factory)
    with factory() as db:
        response = AvailabilityConversationService().respond(
            db,
            session_id=session_id,
            message="Actually Saturday.",
        )

    assert response.status is AvailabilityStatus.NEEDS_CONTEXT
    assert response.slot_ids == ()
    assert "Please specify" in response.text


def test_request_without_service_asks_instead_of_marking_service_invalid(
    database,
) -> None:
    _, factory, _, _ = database
    session_id = _new_session(factory)
    with factory() as db:
        response = AvailabilityConversationService().respond(
            db,
            session_id=session_id,
            message="Do you have an appointment on Friday?",
        )

    assert response.status is AvailabilityStatus.NEEDS_CONTEXT
    assert response.reason == "request_requires_a_service"


def test_explicit_full_date_overrides_date_and_preserves_service(database) -> None:
    _, factory, _, _ = database
    session_id = _new_session(factory)
    conversation = AvailabilityConversationService()
    with factory() as db:
        initial = conversation.respond(
            db,
            session_id=session_id,
            message="Check a haircut appointment for Friday.",
        )
        corrected = conversation.respond(
            db,
            session_id=session_id,
            message="Sorry, I meant 2026-11-07.",
        )
        context = db.get(AvailabilityConversationContext, str(session_id))

    assert initial.requested_date == date(2026, 10, 30)
    assert corrected.status is AvailabilityStatus.NO_RECORDED_SLOTS
    assert corrected.service_id == "haircut"
    assert corrected.requested_date == date(2026, 11, 7)
    assert context is not None
    assert context.requested_date == date(2026, 11, 7)


def test_weekday_resolves_from_pinned_clock_and_explicit_weekday_date(
    database,
) -> None:
    _, factory, _, _ = database
    session_id = _new_session(factory)
    conversation = AvailabilityConversationService()
    with factory() as db:
        relative = conversation.respond(
            db,
            session_id=session_id,
            message="Do you have a haircut appointment Saturday?",
        )
        explicit = conversation.respond(
            db,
            session_id=session_id,
            message="I meant Saturday 2026-10-31.",
        )

    assert relative.requested_date == date(2026, 10, 31)
    assert explicit.requested_date == date(2026, 10, 31)
    assert explicit.status is AvailabilityStatus.AVAILABLE


def test_ambiguous_date_does_not_guess_or_change_context(database) -> None:
    _, factory, _, _ = database
    session_id = _new_session(factory)
    conversation = AvailabilityConversationService()
    with factory() as db:
        first = conversation.respond(
            db,
            session_id=session_id,
            message="Do you have a haircut appointment Friday?",
        )
        ambiguous = conversation.respond(
            db,
            session_id=session_id,
            message="Actually, Friday or Saturday.",
        )
        context = db.get(AvailabilityConversationContext, str(session_id))

    assert first.status is AvailabilityStatus.AVAILABLE
    assert ambiguous.status is AvailabilityStatus.AMBIGUOUS
    assert context is not None
    assert context.requested_date == date(2026, 10, 30)


def test_unknown_service_and_unrelated_text_are_not_routed_to_lookup(
    database,
) -> None:
    _, factory, _, _ = database
    session_id = _new_session(factory)
    conversation = AvailabilityConversationService()
    with factory() as db:
        unknown = conversation.respond(
            db,
            session_id=session_id,
            message="Do you have a hair coloring appointment on Friday?",
        )
        unrelated = conversation.respond(
            db,
            session_id=session_id,
            message="Tell me about the weather.",
        )

    assert unknown.status is AvailabilityStatus.INVALID_SERVICE
    assert unrelated.status is AvailabilityStatus.UNSUPPORTED
    assert unknown.slot_ids == unrelated.slot_ids == ()


def test_context_survives_database_restart(database) -> None:
    engine, factory, database_path, _ = database
    session_id = _new_session(factory)
    with factory() as db:
        first = AvailabilityConversationService().respond(
            db,
            session_id=session_id,
            message="Do you have a haircut appointment Friday?",
        )

    engine.dispose()
    reopened_engine = create_database_engine(
        f"sqlite:///{database_path.as_posix()}"
    )
    try:
        reopened_factory = create_session_factory(reopened_engine)
        with reopened_factory() as db:
            after_restart = AvailabilityConversationService().respond(
                db,
                session_id=session_id,
                message="Sorry, I meant Saturday.",
            )
    finally:
        reopened_engine.dispose()

    assert first.status is AvailabilityStatus.AVAILABLE
    assert after_restart.status is AvailabilityStatus.AVAILABLE
    assert after_restart.service_id == "haircut"
    assert after_restart.requested_date == date(2026, 10, 31)


def test_closed_session_cannot_update_availability_context(database) -> None:
    _, factory, _, _ = database
    session_id = _new_session(factory)
    with factory() as db:
        close_session(
            db,
            session_id=session_id,
            outcome=SessionOutcome.CANCELLED,
        )
        response = AvailabilityConversationService().respond(
            db,
            session_id=session_id,
            message="Sorry, I meant Saturday.",
        )

    assert response.status is AvailabilityStatus.SESSION_CLOSED
    with factory() as db:
        assert db.get(AvailabilityConversationContext, str(session_id)) is None


def test_unknown_session_is_rejected_without_context(database) -> None:
    _, factory, _, _ = database
    with factory() as db:
        response = AvailabilityConversationService().respond(
            db,
            session_id=UUID(int=0),
            message="Do you have a haircut appointment Friday?",
        )

    assert response.status is AvailabilityStatus.SESSION_NOT_FOUND
    assert response.slot_ids == ()


def test_service_lookup_is_deterministic_and_does_not_mutate_fixture() -> None:
    before = CANONICAL_FIXTURE_PATH.read_bytes()
    service = AvailabilityService()
    first = service.lookup(
        service_id="haircut",
        requested_date=date(2026, 10, 30),
    )
    second = service.lookup(
        service_id="haircut",
        requested_date=date(2026, 10, 30),
    )

    assert first == second
    assert CANONICAL_FIXTURE_PATH.read_bytes() == before


def test_context_persistence_does_not_create_booking_or_modify_fixture(
    database,
) -> None:
    _, factory, _, _ = database
    before = CANONICAL_FIXTURE_PATH.read_bytes()
    session_id = _new_session(factory)
    with factory() as db:
        result = AvailabilityConversationService().respond(
            db,
            session_id=session_id,
            message="Do you have a haircut appointment Friday?",
        )
        contexts = list(db.scalars(select(AvailabilityConversationContext)))
        table_names = set(inspect(db.get_bind()).get_table_names())

    assert result.status is AvailabilityStatus.AVAILABLE
    assert len(contexts) == 1
    assert "appointments" not in table_names
    assert CANONICAL_FIXTURE_PATH.read_bytes() == before


def test_invalid_full_date_in_conversation_is_reported(database) -> None:
    _, factory, _, _ = database
    session_id = _new_session(factory)
    with factory() as db:
        response = AvailabilityConversationService().respond(
            db,
            session_id=session_id,
            message="Do you have a haircut appointment on 2026-02-30?",
        )

    assert response.status is AvailabilityStatus.INVALID_DATE
    assert response.slot_ids == ()
