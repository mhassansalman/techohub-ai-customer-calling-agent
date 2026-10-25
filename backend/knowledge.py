from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, timedelta
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.fixtures import (
    BusinessHoursFixture,
    SalonFixtureBundle,
    ServiceFixture,
    load_demo_salon_fixture,
)


DEFAULT_KNOWLEDGE_BUNDLE = Path(__file__).resolve().parents[1] / "knowledge_bundle"
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
_HOURS_TERMS = {"hour", "hours", "open", "opening", "close", "closed", "closing"}
_POLICY_TERMS = {
    "cancel",
    "cancellation",
    "cancellations",
    "deposit",
    "discount",
    "discounts",
    "guarantee",
    "payment",
    "payments",
    "refund",
    "refunds",
}
_SERVICE_QUESTION_TERMS = {
    "available",
    "availability",
    "cost",
    "duration",
    "long",
    "offer",
    "offers",
    "price",
    "provide",
    "service",
    "services",
    "take",
}
_BOOKING_TERMS = {"appointment", "appointments", "booking", "bookings", "slot", "slots"}
_INDEX_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_TOKEN = re.compile(r"[a-z0-9]+")


class KnowledgeCategory(StrEnum):
    HOURS = "hours"
    SERVICE = "service"
    FAQ = "faq"


class RetrievalStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    ABSTAINED = "abstained"


class KnowledgeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    category: KnowledgeCategory
    status: Literal["approved"] = "approved"
    content: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    facts: tuple[tuple[str, str], ...] = ()

    def fact(self, key: str) -> str | None:
        return next((value for fact_key, value in self.facts if fact_key == key), None)


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: RetrievalStatus
    reason: str
    records: tuple[KnowledgeRecord, ...] = ()

    @model_validator(mode="after")
    def validate_evidence(self) -> RetrievalResult:
        if self.status is RetrievalStatus.MATCHED and not self.records:
            raise ValueError("matched retrieval results must include source records")
        if self.status is not RetrievalStatus.MATCHED and self.records:
            raise ValueError("non-matched retrieval results cannot include source records")
        return self

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(record.source_id for record in self.records)


class KnowledgeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1)
    status: AnswerStatus
    reason: str
    source_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_sources(self) -> KnowledgeAnswer:
        if self.status is AnswerStatus.ANSWERED and not self.source_ids:
            raise ValueError("answered knowledge responses must cite source IDs")
        return self


class KnowledgeSourceNotFoundError(LookupError):
    pass


class KnowledgeIndex:
    def __init__(self, records: Iterable[KnowledgeRecord]) -> None:
        record_list = tuple(records)
        records_by_id = {record.source_id: record for record in record_list}
        if not records_by_id:
            raise ValueError("knowledge index must contain at least one approved record")
        if len(records_by_id) != len(record_list):
            raise ValueError("knowledge source IDs must be unique")
        self._records: Mapping[str, KnowledgeRecord] = MappingProxyType(records_by_id)
        self.records = record_list

    def resolve_source_id(self, source_id: str) -> KnowledgeRecord:
        try:
            return self._records[source_id]
        except KeyError as error:
            raise KnowledgeSourceNotFoundError(source_id) from error

    def retrieve(self, query: str, *, fixture: SalonFixtureBundle) -> RetrievalResult:
        tokens = _tokens(query)
        if not tokens:
            return _unsupported("empty_query")

        matched_faqs = _match_faq_records(self.records, query)
        if len(matched_faqs) > 1:
            return _ambiguous("multiple_approved_faqs")
        if matched_faqs:
            return _matched("approved_faq", matched_faqs)

        has_hours_topic = bool(tokens & _HOURS_TERMS)
        service_matches = _match_services(self.records, query)
        has_service_topic = bool(tokens & _SERVICE_QUESTION_TERMS) or bool(
            service_matches
        )
        has_policy_topic = bool(tokens & _POLICY_TERMS)

        if has_policy_topic:
            if has_hours_topic or has_service_topic:
                return _ambiguous("supported_and_unsupported_topics")
            return _unsupported("no_approved_policy_source")

        if has_hours_topic and has_service_topic:
            return _ambiguous("hours_and_service_topics")
        if has_hours_topic:
            if _has_booking_terms(tokens):
                return _unsupported("appointment_slots_require_booking_provider")
            days = _requested_days(tokens, fixture)
            if days is None:
                return _ambiguous("multiple_or_conflicting_days")
            return _hours_result(self.records, days)

        if has_service_topic:
            if _has_booking_terms(tokens):
                return _unsupported("appointment_slots_require_booking_provider")
            if len(service_matches) > 1:
                return _ambiguous("multiple_or_conflicting_services")
            if not service_matches:
                if _is_general_catalog_question(query):
                    return _matched(
                        "service_catalog_list",
                        tuple(
                            record
                            for record in self.records
                            if record.category is KnowledgeCategory.SERVICE
                        ),
                    )
                return _unsupported("unknown_service")
            return _matched("service_catalog", service_matches)

        return _unsupported("no_approved_source_match")


class KnowledgeService:
    def __init__(
        self,
        *,
        index: KnowledgeIndex | None = None,
        fixture: SalonFixtureBundle | None = None,
        bundle_path: Path | None = None,
    ) -> None:
        self.fixture = fixture or load_demo_salon_fixture()
        self.index = index or build_knowledge_index(
            self.fixture,
            bundle_path=bundle_path,
        )

    def retrieve(self, query: str) -> RetrievalResult:
        return self.index.retrieve(query, fixture=self.fixture)

    def answer(self, query: str) -> KnowledgeAnswer:
        return compose_answer(self.retrieve(query))


def build_knowledge_index(
    fixture: SalonFixtureBundle | None = None,
    *,
    bundle_path: Path | None = None,
) -> KnowledgeIndex:
    canonical = fixture or load_demo_salon_fixture()
    records = _fixture_records(canonical)
    if bundle_path is not None:
        records.extend(_approved_markdown_records(bundle_path))
    elif (DEFAULT_KNOWLEDGE_BUNDLE / "index.md").is_file():
        records.extend(_approved_markdown_records(DEFAULT_KNOWLEDGE_BUNDLE))
    return KnowledgeIndex(records)


def compose_answer(result: RetrievalResult) -> KnowledgeAnswer:
    if result.status is not RetrievalStatus.MATCHED:
        return KnowledgeAnswer(
            text=_abstention_text(result.reason),
            status=AnswerStatus.ABSTAINED,
            reason=result.reason,
            source_ids=result.source_ids,
        )

    if result.reason == "approved_faq":
        record = result.records[0]
        return KnowledgeAnswer(
            text=record.content,
            status=AnswerStatus.ANSWERED,
            reason=result.reason,
            source_ids=result.source_ids,
        )

    if result.reason == "service_catalog":
        return _compose_service_answer(result.records[0], result.source_ids)

    if result.reason == "service_catalog_list":
        return _compose_service_list(result.records)

    if result.reason == "business_hours":
        return _compose_hours_answer(result.records, result.source_ids)

    return KnowledgeAnswer(
        text="I could not verify an answer from approved information.",
        status=AnswerStatus.ABSTAINED,
        reason="unsupported_retrieval_result",
        source_ids=(),
    )


def unsupported_faq_categories() -> tuple[str, ...]:
    return (
        "refund and cancellation policies",
        "discounts and promotions",
        "payment methods and deposits",
        "customer-specific information",
        "appointment-slot availability",
    )


def _fixture_records(fixture: SalonFixtureBundle) -> list[KnowledgeRecord]:
    records: list[KnowledgeRecord] = []
    hours_by_day = {item.weekday: item for item in fixture.business_hours}
    for day in _WEEKDAYS:
        hour_record = hours_by_day.get(day)
        if hour_record is None:
            if day != "sunday":
                continue
            records.append(
                KnowledgeRecord(
                    source_id=f"fixture:{fixture.fixture_id}:hours:sunday-closed",
                    source_reference="fixtures/demo_salon.json#/business_hours",
                    category=KnowledgeCategory.HOURS,
                    content="Sunday is closed; the approved weekly hours contain no Sunday entry.",
                    aliases=("sunday", "sundays", "sun"),
                    facts=(("weekday", "sunday"), ("closed", "true")),
                )
            )
            continue
        index = fixture.business_hours.index(hour_record)
        records.append(_hours_record(fixture, hour_record, index))

    for service in fixture.services:
        index = fixture.services.index(service)
        records.append(_service_record(fixture, service, index))
    return records


def _hours_record(
    fixture: SalonFixtureBundle,
    hours: BusinessHoursFixture,
    index: int,
) -> KnowledgeRecord:
    day = hours.weekday
    return KnowledgeRecord(
        source_id=f"fixture:{fixture.fixture_id}:hours:{day}",
        source_reference=f"fixtures/demo_salon.json#/business_hours/{index}",
        category=KnowledgeCategory.HOURS,
        content=(
            f"{day.title()} hours are {hours.opens_at.strftime('%H:%M')}–"
            f"{hours.closes_at.strftime('%H:%M')} Etc/UTC."
        ),
        aliases=(day, *_day_aliases(day)),
        facts=(
            ("weekday", day),
            ("opens_at", hours.opens_at.strftime("%H:%M")),
            ("closes_at", hours.closes_at.strftime("%H:%M")),
        ),
    )


def _service_record(
    fixture: SalonFixtureBundle,
    service: ServiceFixture,
    index: int,
) -> KnowledgeRecord:
    aliases = _service_aliases(service)
    price = f"{service.price_amount:.2f}"
    return KnowledgeRecord(
        source_id=f"fixture:{fixture.fixture_id}:service:{service.service_id}",
        source_reference=f"fixtures/demo_salon.json#/services/{index}",
        category=KnowledgeCategory.SERVICE,
        content=(
            f"{service.name}: {service.duration_minutes} minutes, "
            f"{service.currency} {price}; "
            f"{'active' if service.active else 'inactive'} in the service catalog."
        ),
        aliases=aliases,
        facts=(
            ("service_id", service.service_id),
            ("name", service.name),
            ("duration_minutes", str(service.duration_minutes)),
            ("price_amount", price),
            ("currency", service.currency),
            ("active", str(service.active).lower()),
        ),
    )


def _approved_markdown_records(bundle_path: Path) -> list[KnowledgeRecord]:
    root = bundle_path.resolve(strict=True)
    index_path = root / "index.md"
    if not index_path.is_file():
        raise FileNotFoundError(f"OKF entry point does not exist: {index_path}")

    records: list[KnowledgeRecord] = []
    seen_paths: set[Path] = set()
    for target in _INDEX_LINK.findall(index_path.read_text(encoding="utf-8")):
        parsed = urlparse(target)
        if parsed.scheme or parsed.netloc or not parsed.path.lower().endswith(".md"):
            continue
        relative_path = Path(parsed.path)
        if relative_path.is_absolute():
            raise ValueError(f"OKF index link must be relative: {target}")
        document_path = (root / relative_path).resolve(strict=True)
        if not document_path.is_relative_to(root):
            raise ValueError(f"OKF index link escapes its bundle: {target}")
        if document_path == index_path or document_path in seen_paths:
            continue
        seen_paths.add(document_path)
        record = _markdown_faq_record(root, document_path)
        if record is not None:
            records.append(record)
    return records


def _markdown_faq_record(root: Path, document_path: Path) -> KnowledgeRecord | None:
    text = document_path.read_text(encoding="utf-8")
    metadata, content = _parse_frontmatter(text, document_path)
    if metadata.get("status") != "approved":
        raise ValueError(f"OKF record is not approved: {document_path}")
    relative_path = document_path.relative_to(root)
    is_faq_record = (
        metadata.get("type") == "faq"
        or metadata.get("category") == "faq"
        or relative_path.parts[0].casefold() == "faq"
    )
    if not is_faq_record:
        return None

    source_id = metadata.get("source_id")
    title = metadata.get("title")
    version = metadata.get("version")
    if not all(isinstance(value, str) and value.strip() for value in (source_id, title, version)):
        raise ValueError(f"OKF FAQ metadata is incomplete: {document_path}")
    keywords = metadata.get("keywords", metadata.get("aliases", ()))
    if isinstance(keywords, str):
        keywords = (keywords,)
    if not isinstance(keywords, (list, tuple)) or any(
        not isinstance(item, str) or not item.strip() for item in keywords
    ):
        raise ValueError(f"OKF FAQ keywords must be a list of strings: {document_path}")
    factual_content = content.strip()
    if not factual_content:
        raise ValueError(f"OKF FAQ content is empty: {document_path}")
    reference = relative_path.as_posix()
    return KnowledgeRecord(
        source_id=source_id,
        source_reference=f"{reference}#version={version}",
        category=KnowledgeCategory.FAQ,
        content=factual_content,
        aliases=tuple(dict.fromkeys((title, *keywords))),
    )


def _parse_frontmatter(
    text: str,
    source_path: Path,
) -> tuple[dict[str, object], str]:
    if not text.startswith("---\n"):
        raise ValueError(f"OKF record has no YAML frontmatter: {source_path}")
    _, separator, remainder = text[4:].partition("\n---\n")
    if not separator:
        raise ValueError(f"OKF frontmatter is not terminated: {source_path}")
    try:
        metadata = yaml.safe_load(text[4 : text.index("\n---\n", 4)])
    except (yaml.YAMLError, ValueError) as error:
        raise ValueError(f"Invalid OKF YAML frontmatter: {source_path}") from error
    if not isinstance(metadata, dict) or any(
        not isinstance(key, str) for key in metadata
    ):
        raise ValueError(f"OKF frontmatter must be a string-keyed mapping: {source_path}")
    return metadata, remainder


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.casefold()))


def _token_sequence(text: str) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(text.casefold()))


def _contains_phrase(tokens: tuple[str, ...], phrase: str) -> bool:
    phrase_tokens = _token_sequence(phrase)
    return bool(phrase_tokens) and any(
        tokens[start : start + len(phrase_tokens)] == phrase_tokens
        for start in range(len(tokens) - len(phrase_tokens) + 1)
    )


def _day_aliases(day: str) -> tuple[str, ...]:
    return tuple(alias for alias, full_day in _DAY_ALIASES.items() if full_day == day)


def _requested_days(
    tokens: set[str],
    fixture: SalonFixtureBundle,
) -> tuple[str, ...] | None:
    requested = {
        full_day
        for alias, full_day in _DAY_ALIASES.items()
        if alias in tokens
    }
    requested.update(day for day in _WEEKDAYS if day in tokens)
    relative_days: set[str] = set()
    pinned_date = fixture.pinned_clock.astimezone(UTC).date()
    if "today" in tokens:
        relative_days.add(pinned_date.strftime("%A").lower())
    if "tomorrow" in tokens:
        relative_days.add((pinned_date + timedelta(days=1)).strftime("%A").lower())
    if requested and relative_days:
        return None
    days = requested or relative_days
    if len(days) > 1:
        return None
    if days:
        return (next(iter(days)),)
    return tuple(_WEEKDAYS[:5]) if "weekdays" in tokens else _WEEKDAYS


def _match_services(
    records: tuple[KnowledgeRecord, ...],
    query: str,
) -> tuple[KnowledgeRecord, ...]:
    tokens = _token_sequence(query)
    matches: list[tuple[int, int, KnowledgeRecord]] = []
    for record in records:
        if record.category is not KnowledgeCategory.SERVICE:
            continue
        for alias in record.aliases:
            alias_tokens = _token_sequence(alias)
            if not alias_tokens:
                continue
            for start in range(len(tokens) - len(alias_tokens) + 1):
                if tokens[start : start + len(alias_tokens)] == alias_tokens:
                    matches.append((start, start + len(alias_tokens), record))

    selected_spans: list[tuple[int, int]] = []
    selected_records: dict[str, KnowledgeRecord] = {}
    for start, end, record in sorted(
        matches,
        key=lambda item: (item[0], -(item[1] - item[0]), item[2].source_id),
    ):
        if any(start < selected_end and end > selected_start
               for selected_start, selected_end in selected_spans):
            continue
        selected_spans.append((start, end))
        selected_records[record.source_id] = record
    return tuple(selected_records.values())


def _match_faq_records(
    records: tuple[KnowledgeRecord, ...],
    query: str,
) -> tuple[KnowledgeRecord, ...]:
    ordered_tokens = _token_sequence(query)
    matched: list[KnowledgeRecord] = []
    for record in records:
        if record.category is not KnowledgeCategory.FAQ:
            continue
        if any(_contains_phrase(ordered_tokens, alias) for alias in record.aliases):
            matched.append(record)
    return tuple(matched)


def _is_general_catalog_question(query: str) -> bool:
    tokens = _token_sequence(query)
    return any(
        _contains_phrase(tokens, phrase)
        for phrase in (
            "what services",
            "which services",
            "list services",
            "service catalog",
            "catalog of services",
            "services do you offer",
            "services do you provide",
            "what services are available",
            "available services",
        )
    )


def _has_booking_terms(tokens: set[str]) -> bool:
    return bool(tokens & _BOOKING_TERMS)


def _hours_result(
    records: tuple[KnowledgeRecord, ...],
    days: tuple[str, ...],
) -> RetrievalResult:
    by_day = {
        record.fact("weekday"): record
        for record in records
        if record.category is KnowledgeCategory.HOURS
    }
    selected = tuple(by_day[day] for day in days if day in by_day)
    if len(selected) != len(days):
        return _unsupported("hours_not_available_in_fixture")
    return _matched("business_hours", selected)


def _matched(
    reason: str,
    records: Iterable[KnowledgeRecord],
) -> RetrievalResult:
    return RetrievalResult(
        status=RetrievalStatus.MATCHED,
        reason=reason,
        records=tuple(records),
    )


def _ambiguous(reason: str) -> RetrievalResult:
    return RetrievalResult(status=RetrievalStatus.AMBIGUOUS, reason=reason)


def _unsupported(reason: str) -> RetrievalResult:
    return RetrievalResult(status=RetrievalStatus.UNSUPPORTED, reason=reason)


def _compose_hours_answer(
    records: tuple[KnowledgeRecord, ...],
    source_ids: tuple[str, ...],
) -> KnowledgeAnswer:
    if len(records) == 1:
        record = records[0]
        weekday = record.fact("weekday")
        if record.fact("closed") == "true":
            text = f"Demo Salon is closed on {weekday.title()}."
        else:
            text = (
                f"Demo Salon is open on {weekday.title()}, {record.fact('opens_at')}–"
                f"{record.fact('closes_at')} Etc/UTC."
            )
    else:
        groups = _group_consecutive_hours(records)
        open_groups = [
            _format_hours_group(group)
            for group in groups
            if group[0].fact("closed") != "true"
        ]
        closed_groups = [
            _day_group_label(group)
            for group in groups
            if group[0].fact("closed") == "true"
        ]
        if open_groups:
            text = f"Demo Salon is open {'; '.join(open_groups)}"
            if closed_groups:
                text += f"; and closed {', '.join(closed_groups)}"
            text += "."
        else:
            text = f"Demo Salon is closed {', '.join(closed_groups)}."
    return KnowledgeAnswer(
        text=text,
        status=AnswerStatus.ANSWERED,
        reason="business_hours",
        source_ids=source_ids,
    )


def _group_consecutive_hours(
    records: tuple[KnowledgeRecord, ...],
) -> tuple[tuple[KnowledgeRecord, ...], ...]:
    groups: list[list[KnowledgeRecord]] = []
    for record in records:
        if groups and _same_schedule(groups[-1][-1], record):
            groups[-1].append(record)
        else:
            groups.append([record])
    return tuple(tuple(group) for group in groups)


def _same_schedule(first: KnowledgeRecord, second: KnowledgeRecord) -> bool:
    first_day = first.fact("weekday")
    second_day = second.fact("weekday")
    if first_day is None or second_day is None:
        return False
    if _WEEKDAYS.index(second_day) != _WEEKDAYS.index(first_day) + 1:
        return False
    return (
        first.fact("closed"),
        first.fact("opens_at"),
        first.fact("closes_at"),
    ) == (
        second.fact("closed"),
        second.fact("opens_at"),
        second.fact("closes_at"),
    )


def _day_group_label(records: tuple[KnowledgeRecord, ...]) -> str:
    start = (records[0].fact("weekday") or "").title()
    end = (records[-1].fact("weekday") or "").title()
    return start if start == end else f"{start}–{end}"


def _format_hours_group(records: tuple[KnowledgeRecord, ...]) -> str:
    return (
        f"{_day_group_label(records)}, {records[0].fact('opens_at')}–"
        f"{records[0].fact('closes_at')} Etc/UTC"
    )


def _compose_service_answer(
    record: KnowledgeRecord,
    source_ids: tuple[str, ...],
) -> KnowledgeAnswer:
    name = record.fact("name")
    if record.fact("active") != "true":
        text = f"{name} is not listed as an active service in the approved catalog."
    else:
        text = (
            f"{name} is offered in the Demo Salon service catalog. "
            f"It costs {record.fact('currency')} {record.fact('price_amount')} "
            f"and takes {record.fact('duration_minutes')} minutes. "
            "Catalog listing does not confirm appointment-slot availability."
        )
    return KnowledgeAnswer(
        text=text,
        status=AnswerStatus.ANSWERED,
        reason="service_catalog",
        source_ids=source_ids,
    )


def _compose_service_list(
    records: tuple[KnowledgeRecord, ...],
) -> KnowledgeAnswer:
    active_services = tuple(
        record
        for record in records
        if record.fact("active") == "true"
    )
    if not active_services:
        return KnowledgeAnswer(
            text="I don't have an active service catalog to confirm.",
            status=AnswerStatus.ABSTAINED,
            reason="no_active_services",
        )
    service_names = ", ".join(record.fact("name") or "" for record in active_services)
    return KnowledgeAnswer(
        text=f"Services listed in the approved Demo Salon catalog: {service_names}.",
        status=AnswerStatus.ANSWERED,
        reason="service_catalog_list",
        source_ids=tuple(record.source_id for record in active_services),
    )


def _abstention_text(reason: str) -> str:
    if reason == "no_approved_policy_source":
        return "I don't have approved information to confirm that policy."
    if reason == "unknown_service":
        return (
            "I don't have approved information about that service, so I can't "
            "confirm whether it's offered or quote its price or duration."
        )
    if reason == "appointment_slots_require_booking_provider":
        return "I can't confirm appointment slots from the service catalog."
    if reason in {
        "hours_and_service_topics",
        "multiple_or_conflicting_days",
        "multiple_or_conflicting_services",
        "supported_and_unsupported_topics",
        "multiple_approved_faqs",
    }:
        return "I'm not sure which approved information you mean. Please clarify."
    return "I don't have approved information to answer that question."


def _service_aliases(service: ServiceFixture) -> tuple[str, ...]:
    aliases = [service.name]
    if service.service_id == "haircut":
        aliases.append("hair cut")
    elif service.service_id == "beard-trim":
        aliases.append("beard trim")
    elif service.service_id == "haircut-beard":
        aliases.extend(
            (
                "haircut and beard trim",
                "haircut beard trim",
                "haircut and beard",
            )
        )
    return tuple(dict.fromkeys(aliases))
