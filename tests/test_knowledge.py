from __future__ import annotations

from pathlib import Path

import pytest

from backend.fixtures import CANONICAL_FIXTURE_PATH, load_demo_salon_fixture
from backend.knowledge import (
    AnswerStatus,
    KnowledgeCategory,
    KnowledgeService,
    RetrievalStatus,
    build_knowledge_index,
    unsupported_faq_categories,
)


@pytest.fixture
def knowledge() -> KnowledgeService:
    return KnowledgeService()


@pytest.mark.parametrize(
    ("query", "expected_hours"),
    [
        ("What are your Monday hours?", "09:00–18:00"),
        ("When do you open on Tuesday?", "09:00–18:00"),
        ("How late are you open Wednesday?", "09:00–18:00"),
        ("What time do you close Thursday?", "09:00–18:00"),
        ("Are you open Friday?", "09:00–18:00"),
        ("What are your Saturday hours?", "10:00–16:00"),
    ],
)
def test_day_specific_canonical_hours(
    knowledge: KnowledgeService,
    query: str,
    expected_hours: str,
) -> None:
    answer = knowledge.answer(query)

    assert answer.status is AnswerStatus.ANSWERED
    assert expected_hours in answer.text
    assert answer.source_ids
    assert all(
        knowledge.index.resolve_source_id(source_id).category
        is KnowledgeCategory.HOURS
        for source_id in answer.source_ids
    )


def test_sunday_is_grounded_as_closed(knowledge: KnowledgeService) -> None:
    answer = knowledge.answer("Are you open on Sunday?")

    assert answer.status is AnswerStatus.ANSWERED
    assert answer.text == "Demo Salon is closed on Sunday."
    assert answer.source_ids == ("fixture:demo-salon-v1:hours:sunday-closed",)
    record = knowledge.index.resolve_source_id(answer.source_ids[0])
    assert record.source_reference == "fixtures/demo_salon.json#/business_hours"


def test_t02_approved_hours_answer_cites_canonical_source_records(
    knowledge: KnowledgeService,
) -> None:
    answer = knowledge.answer("What are your opening hours?")

    assert answer.status is AnswerStatus.ANSWERED
    assert "Monday–Friday, 09:00–18:00 Etc/UTC" in answer.text
    assert "Saturday, 10:00–16:00 Etc/UTC" in answer.text
    assert "closed Sunday" in answer.text
    assert len(answer.source_ids) == 7


def test_pinned_clock_resolves_relative_days_in_utc(
    knowledge: KnowledgeService,
) -> None:
    today = knowledge.answer("Are you open today?")
    tomorrow = knowledge.answer("What time do you close tomorrow?")

    assert "Thursday, 09:00–18:00 Etc/UTC" in today.text
    assert today.source_ids == ("fixture:demo-salon-v1:hours:thursday",)
    assert "Friday, 09:00–18:00 Etc/UTC" in tomorrow.text
    assert tomorrow.source_ids == ("fixture:demo-salon-v1:hours:friday",)


@pytest.mark.parametrize(
    ("query", "service_name", "price", "duration"),
    [
        ("How much is a haircut and how long does it take?", "Haircut", "USD 35.00", "30"),
        ("What is the price and duration of a beard trim?", "Beard trim", "USD 18.00", "20"),
        (
            "How much does a haircut and beard trim cost and how long is it?",
            "Haircut and beard trim",
            "USD 45.00",
            "45",
        ),
    ],
)
def test_service_price_and_duration_are_fixture_grounded(
    knowledge: KnowledgeService,
    query: str,
    service_name: str,
    price: str,
    duration: str,
) -> None:
    answer = knowledge.answer(query)

    assert answer.status is AnswerStatus.ANSWERED
    assert service_name in answer.text
    assert price in answer.text
    assert f"{duration} minutes" in answer.text
    assert len(answer.source_ids) == 1
    record = knowledge.index.resolve_source_id(answer.source_ids[0])
    assert record.category is KnowledgeCategory.SERVICE


def test_service_catalog_answer_does_not_claim_live_slots(
    knowledge: KnowledgeService,
) -> None:
    answer = knowledge.answer("Do you offer a haircut?")

    assert answer.status is AnswerStatus.ANSWERED
    assert "offered in the Demo Salon service catalog" in answer.text
    assert "does not confirm appointment-slot availability" in answer.text


def test_general_service_catalog_is_grounded(
    knowledge: KnowledgeService,
) -> None:
    answer = knowledge.answer("What services do you offer?")

    assert answer.status is AnswerStatus.ANSWERED
    assert all(
        name in answer.text
        for name in ("Haircut", "Beard trim", "Haircut and beard trim")
    )
    assert len(answer.source_ids) == 3


def test_unknown_service_is_not_presented_as_unavailable(
    knowledge: KnowledgeService,
) -> None:
    result = knowledge.retrieve("Do you offer hair coloring?")
    answer = knowledge.answer("Do you offer hair coloring?")

    assert result.status is RetrievalStatus.UNSUPPORTED
    assert result.reason == "unknown_service"
    assert answer.status is AnswerStatus.ABSTAINED
    assert "can't confirm whether it's offered" in answer.text
    assert answer.source_ids == ()


def test_t03_unknown_policy_abstains_without_inventing_a_rule(
    knowledge: KnowledgeService,
) -> None:
    result = knowledge.retrieve("Can I get a refund?")
    answer = knowledge.answer("Can I get a refund?")

    assert result.status is RetrievalStatus.UNSUPPORTED
    assert result.reason == "no_approved_policy_source"
    assert answer.status is AnswerStatus.ABSTAINED
    assert "approved information" in answer.text
    assert answer.source_ids == ()
    assert "refund and cancellation policies" in unsupported_faq_categories()


def test_default_index_contains_only_canonical_fixture_knowledge(
    knowledge: KnowledgeService,
) -> None:
    assert all(
        record.category in {KnowledgeCategory.HOURS, KnowledgeCategory.SERVICE}
        and record.status == "approved"
        for record in knowledge.index.records
    )


def test_conflicting_service_names_abstain(
    knowledge: KnowledgeService,
) -> None:
    result = knowledge.retrieve("Compare a haircut or beard trim.")
    answer = knowledge.answer("Compare a haircut or beard trim.")

    assert result.status is RetrievalStatus.AMBIGUOUS
    assert result.reason == "multiple_or_conflicting_services"
    assert answer.status is AnswerStatus.ABSTAINED
    assert answer.source_ids == ()


def test_mixed_hours_and_unsupported_policy_abstains(
    knowledge: KnowledgeService,
) -> None:
    result = knowledge.retrieve("What are your hours and cancellation policy?")

    assert result.status is RetrievalStatus.AMBIGUOUS
    assert result.reason == "supported_and_unsupported_topics"


def test_appointment_slots_are_not_answered_from_static_knowledge(
    knowledge: KnowledgeService,
) -> None:
    answer = knowledge.answer("Do you have an appointment slot for a haircut?")

    assert answer.status is AnswerStatus.ABSTAINED
    assert answer.reason == "appointment_slots_require_booking_provider"
    assert "can't confirm appointment slots" in answer.text


def test_matcher_uses_token_boundaries_not_substrings(
    knowledge: KnowledgeService,
) -> None:
    result = knowledge.retrieve("What is the price of a haircutters service?")

    assert result.status is RetrievalStatus.UNSUPPORTED
    assert result.reason == "unknown_service"


def test_retrieval_is_deterministic_and_sources_resolve(
    knowledge: KnowledgeService,
) -> None:
    first = knowledge.retrieve("How much is a haircut?")
    second = knowledge.retrieve("How much is a haircut?")

    assert first == second
    assert first.source_ids == ("fixture:demo-salon-v1:service:haircut",)
    resolved = knowledge.index.resolve_source_id(first.source_ids[0])
    assert resolved.source_reference == "fixtures/demo_salon.json#/services/0"
    with pytest.raises(LookupError, match="not-a-real-source"):
        knowledge.index.resolve_source_id("not-a-real-source")


def test_index_and_repeated_queries_do_not_mutate_canonical_fixture(
    knowledge: KnowledgeService,
) -> None:
    before = CANONICAL_FIXTURE_PATH.read_bytes()
    knowledge.answer("What are your hours?")
    knowledge.answer("Do you offer a haircut?")
    fixture = load_demo_salon_fixture()
    with pytest.raises(ValueError):
        fixture.salon_name = "Changed Salon"  # type: ignore[misc]

    assert CANONICAL_FIXTURE_PATH.read_bytes() == before


def test_okf_index_loads_only_linked_approved_faq_records(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "knowledge_bundle"
    faq_dir = bundle / "faq"
    faq_dir.mkdir(parents=True)
    (bundle / "index.md").write_text(
        "# Approved knowledge\n\n[Example policy](faq/example.md)\n",
        encoding="utf-8",
    )
    (faq_dir / "example.md").write_text(
        "---\n"
        "type: reference\n"
        "title: Appointment policy\n"
        "source_id: kb:faq:appointment-policy\n"
        "version: 1.0.0\n"
        "status: approved\n"
        "keywords:\n"
        "  - appointment policy\n"
        "---\n"
        "TEST ONLY: This approved sample has no real business policy content.\n",
        encoding="utf-8",
    )
    service = KnowledgeService(bundle_path=bundle)

    answer = service.answer("What is the appointment policy?")

    assert answer.status is AnswerStatus.ANSWERED
    assert answer.text.startswith("TEST ONLY:")
    assert answer.source_ids == ("kb:faq:appointment-policy",)
    record = service.index.resolve_source_id(answer.source_ids[0])
    assert record.source_reference == "faq/example.md#version=1.0.0"


def test_okf_index_rejects_linked_unapproved_faq(tmp_path: Path) -> None:
    bundle = tmp_path / "knowledge_bundle"
    bundle.mkdir()
    (bundle / "index.md").write_text("[Draft](draft.md)\n", encoding="utf-8")
    (bundle / "draft.md").write_text(
        "---\n"
        "type: faq\n"
        "title: Draft policy\n"
        "source_id: kb:faq:draft\n"
        "version: 0.1.0\n"
        "status: draft\n"
        "---\n"
        "Draft content.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not approved"):
        build_knowledge_index(bundle_path=bundle)


def test_okf_index_rejects_paths_escaping_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "knowledge_bundle"
    bundle.mkdir()
    (bundle / "index.md").write_text("[Escape](../outside.md)\n", encoding="utf-8")
    (tmp_path / "outside.md").write_text("outside\n", encoding="utf-8")

    with pytest.raises(ValueError, match="escapes its bundle"):
        build_knowledge_index(bundle_path=bundle)


def test_hours_with_two_days_is_ambiguous(knowledge: KnowledgeService) -> None:
    answer = knowledge.answer("What are your hours on Saturday and Sunday?")

    assert answer.status is AnswerStatus.ABSTAINED
    assert answer.reason == "multiple_or_conflicting_days"
