from __future__ import annotations

import json
from datetime import datetime, time
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CANONICAL_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "demo_salon.json"


class FixtureKind(StrEnum):
    CANONICAL = "canonical"
    TEST_ONLY = "test_only"


class FrozenFixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BusinessHoursFixture(FrozenFixtureModel):
    weekday: Literal[
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    opens_at: time
    closes_at: time

    @model_validator(mode="after")
    def validate_opening_interval(self) -> BusinessHoursFixture:
        if self.opens_at >= self.closes_at:
            raise ValueError("opens_at must be earlier than closes_at")
        return self


class ServiceFixture(FrozenFixtureModel):
    service_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    duration_minutes: int = Field(gt=0)
    active: bool


class AvailabilitySlotFixture(FrozenFixtureModel):
    slot_id: str = Field(min_length=1)
    service_id: str = Field(min_length=1)
    starts_at: datetime
    ends_at: datetime
    capacity: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_interval(self) -> AvailabilitySlotFixture:
        if self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None:
            raise ValueError("starts_at must be timezone-aware")
        if self.ends_at.tzinfo is None or self.ends_at.utcoffset() is None:
            raise ValueError("ends_at must be timezone-aware")
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be earlier than ends_at")
        return self


class AppointmentFixture(FrozenFixtureModel):
    appointment_id: str = Field(min_length=1)
    service_id: str = Field(min_length=1)
    starts_at: datetime
    ends_at: datetime
    status: Literal["proposed", "confirmed", "cancelled", "rescheduled"]
    customer_id: str | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> AppointmentFixture:
        if self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None:
            raise ValueError("starts_at must be timezone-aware")
        if self.ends_at.tzinfo is None or self.ends_at.utcoffset() is None:
            raise ValueError("ends_at must be timezone-aware")
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be earlier than ends_at")
        return self


class SalonFixtureBundle(FrozenFixtureModel):
    schema_version: Literal["1"]
    fixture_kind: FixtureKind
    fixture_id: str = Field(min_length=1)
    salon_name: str = Field(min_length=1)
    pinned_clock: datetime
    business_hours: tuple[BusinessHoursFixture, ...]
    services: tuple[ServiceFixture, ...]
    availability_slots: tuple[AvailabilitySlotFixture, ...]
    appointments: tuple[AppointmentFixture, ...]

    @model_validator(mode="after")
    def validate_fixture(self) -> SalonFixtureBundle:
        if self.pinned_clock.tzinfo is None or self.pinned_clock.utcoffset() is None:
            raise ValueError("pinned_clock must be timezone-aware")

        service_ids = [service.service_id for service in self.services]
        if len(service_ids) != len(set(service_ids)):
            raise ValueError("service_id values must be unique")

        slot_ids = [slot.slot_id for slot in self.availability_slots]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("slot_id values must be unique")

        appointment_ids = [item.appointment_id for item in self.appointments]
        if len(appointment_ids) != len(set(appointment_ids)):
            raise ValueError("appointment_id values must be unique")

        known_service_ids = set(service_ids)
        for item in (*self.availability_slots, *self.appointments):
            if item.service_id not in known_service_ids:
                raise ValueError(f"unknown service_id: {item.service_id}")
        return self


def load_fixture(
    path: Path,
    *,
    expected_kind: FixtureKind = FixtureKind.CANONICAL,
) -> SalonFixtureBundle:
    """Read and validate fixture JSON without exposing a write operation."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixture = SalonFixtureBundle.model_validate(payload)
    if fixture.fixture_kind is not expected_kind:
        raise ValueError(
            f"Expected a {expected_kind.value!r} fixture, "
            f"found {fixture.fixture_kind.value!r}"
        )
    return fixture


def load_demo_salon_fixture(
    path: Path | None = None,
) -> SalonFixtureBundle:
    """Load the approved canonical fixture; never substitute test-only data."""
    return load_fixture(
        path or CANONICAL_FIXTURE_PATH,
        expected_kind=FixtureKind.CANONICAL,
    )
