import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.fixtures import (
    CANONICAL_FIXTURE_PATH,
    FixtureKind,
    SalonFixtureBundle,
    availability_for_date,
    demo_clock,
    load_demo_salon_fixture,
    load_fixture,
)


def test_test_only_fixture_validates_and_is_immutable(tmp_path: Path) -> None:
    payload = {
        "schema_version": "1",
        "fixture_kind": "test_only",
        "fixture_id": "test-only-salon",
        "salon_name": "TEST ONLY - not canonical salon data",
        "time_zone": "Etc/UTC",
        "pinned_clock": "2030-01-02T03:04:05+00:00",
        "business_hours": [
            {
                "weekday": "wednesday",
                "opens_at": "10:00:00",
                "closes_at": "11:00:00",
            }
        ],
        "services": [
            {
                "service_id": "test-service",
                "name": "TEST ONLY service",
                "duration_minutes": 30,
                "price_amount": "1.00",
                "currency": "USD",
                "active": True,
            }
        ],
        "availability_slots": [
            {
                "slot_id": "test-slot",
                "service_id": "test-service",
                "starts_at": "2030-01-02T10:00:00+00:00",
                "ends_at": "2030-01-02T10:30:00+00:00",
                "capacity": 1,
            }
        ],
        "appointments": [
            {
                "appointment_id": "test-appointment",
                "service_id": "test-service",
                "starts_at": "2030-01-02T10:00:00+00:00",
                "ends_at": "2030-01-02T10:30:00+00:00",
                "status": "confirmed",
                "customer_id": "test-only-customer",
            }
        ],
    }
    fixture_path = tmp_path / "test_only_fixture.json"
    original_bytes = json.dumps(payload).encode("utf-8")
    fixture_path.write_bytes(original_bytes)

    fixture = load_fixture(fixture_path, expected_kind=FixtureKind.TEST_ONLY)

    assert fixture.pinned_clock == datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert fixture.services[0].service_id == "test-service"
    assert fixture.availability_slots[0].service_id == "test-service"
    assert fixture_path.read_bytes() == original_bytes
    with pytest.raises(ValidationError):
        fixture.salon_name = "changed"
    with pytest.raises(ValidationError):
        fixture.services[0].name = "changed"


def test_canonical_loader_does_not_fall_back_to_test_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(FileNotFoundError):
        load_demo_salon_fixture(tmp_path / "missing_canonical_fixture.json")

    missing_canonical_path = tmp_path / "missing_demo_salon.json"
    monkeypatch.setattr(
        "backend.fixtures.CANONICAL_FIXTURE_PATH", missing_canonical_path
    )
    with pytest.raises(FileNotFoundError):
        load_demo_salon_fixture()
    assert not missing_canonical_path.exists()


def test_test_only_data_cannot_be_loaded_as_canonical(tmp_path: Path) -> None:
    fixture_path = tmp_path / "test_only_fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "fixture_kind": "test_only",
                "fixture_id": "test-only",
                "salon_name": "TEST ONLY",
                "time_zone": "Etc/UTC",
                "pinned_clock": "2030-01-02T03:04:05+00:00",
                "business_hours": [],
                "services": [],
                "availability_slots": [],
                "appointments": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Expected a 'canonical' fixture"):
        load_fixture(fixture_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pinned_clock", "2030-01-02T03:04:05"),
        (
            "services",
            [
                {
                    "service_id": "x",
                    "name": "x",
                    "duration_minutes": 0,
                    "price_amount": "1.00",
                    "currency": "USD",
                    "active": True,
                }
            ],
        ),
        (
            "business_hours",
            [
                {
                    "weekday": "monday",
                    "opens_at": "12:00:00",
                    "closes_at": "11:00:00",
                }
            ],
        ),
    ],
)
def test_invalid_test_only_fixture_values_are_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    payload: dict[str, object] = {
        "schema_version": "1",
        "fixture_kind": "test_only",
        "fixture_id": "test-only",
        "salon_name": "TEST ONLY",
        "time_zone": "Etc/UTC",
        "pinned_clock": "2030-01-02T03:04:05+00:00",
        "business_hours": [],
        "services": [],
        "availability_slots": [],
        "appointments": [],
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        SalonFixtureBundle.model_validate(payload)


def test_fixture_rejects_unknown_service_references() -> None:
    payload = {
        "schema_version": "1",
        "fixture_kind": "test_only",
        "fixture_id": "test-only",
        "salon_name": "TEST ONLY",
        "time_zone": "Etc/UTC",
        "pinned_clock": "2030-01-02T03:04:05+00:00",
        "business_hours": [],
        "services": [],
        "availability_slots": [
            {
                "slot_id": "test-slot",
                "service_id": "missing-service",
                "starts_at": "2030-01-02T10:00:00+00:00",
                "ends_at": "2030-01-02T10:30:00+00:00",
                "capacity": 1,
            }
        ],
        "appointments": [],
    }

    with pytest.raises(ValidationError, match="unknown service_id"):
        SalonFixtureBundle.model_validate(payload)


def test_canonical_fixture_uses_approved_values_and_fixed_clock() -> None:
    original_bytes = CANONICAL_FIXTURE_PATH.read_bytes()
    fixture = load_demo_salon_fixture()

    assert fixture.salon_name == "Demo Salon"
    assert fixture.time_zone == "Etc/UTC"
    assert demo_clock(fixture) == datetime(2026, 10, 29, 9, tzinfo=timezone.utc)
    saturday_hours = next(
        hours for hours in fixture.business_hours if hours.weekday == "saturday"
    )
    assert saturday_hours.opens_at.isoformat() == "10:00:00"
    assert saturday_hours.closes_at.isoformat() == "16:00:00"
    assert [
        (service.service_id, service.price_amount, service.currency)
        for service in fixture.services
    ] == [
        ("haircut", Decimal("35.00"), "USD"),
        ("beard-trim", Decimal("18.00"), "USD"),
        ("haircut-beard", Decimal("45.00"), "USD"),
    ]
    assert CANONICAL_FIXTURE_PATH.read_bytes() == original_bytes


def test_friday_to_saturday_correction_uses_only_recorded_slots() -> None:
    fixture = load_demo_salon_fixture()

    friday_slots = availability_for_date(
        fixture, service_id="haircut", requested_date=date(2026, 10, 30)
    )
    corrected_saturday_slots = availability_for_date(
        fixture, service_id="haircut", requested_date=date(2026, 10, 31)
    )
    unrecorded_slots = availability_for_date(
        fixture, service_id="haircut", requested_date=date(2026, 11, 1)
    )

    assert [slot.starts_at.isoformat() for slot in friday_slots] == [
        "2026-10-30T10:00:00+00:00",
        "2026-10-30T14:00:00+00:00",
    ]
    assert [slot.starts_at.isoformat() for slot in corrected_saturday_slots] == [
        "2026-10-31T10:00:00+00:00"
    ]
    assert unrecorded_slots == ()


def test_fixed_demo_clock_and_queries_do_not_modify_fixture_source() -> None:
    original_bytes = CANONICAL_FIXTURE_PATH.read_bytes()

    fixture = load_demo_salon_fixture()
    clock_first_read = demo_clock(fixture)
    availability_for_date(
        fixture, service_id="haircut", requested_date=date(2026, 10, 31)
    )
    clock_second_read = demo_clock(load_demo_salon_fixture())

    assert clock_first_read == clock_second_read
    assert clock_first_read.date() == date(2026, 10, 29)
    assert CANONICAL_FIXTURE_PATH.read_bytes() == original_bytes


def test_fixture_rejects_non_utc_pinned_clock() -> None:
    payload = {
        "schema_version": "1",
        "fixture_kind": "test_only",
        "fixture_id": "test-only",
        "salon_name": "TEST ONLY",
        "time_zone": "Etc/UTC",
        "pinned_clock": "2030-01-02T03:04:05+01:00",
        "business_hours": [],
        "services": [],
        "availability_slots": [],
        "appointments": [],
    }

    with pytest.raises(ValidationError, match="pinned_clock must use UTC"):
        SalonFixtureBundle.model_validate(payload)
