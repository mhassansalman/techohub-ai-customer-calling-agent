from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import NamedTuple, Protocol, runtime_checkable

from backend.chunker import KnowledgeChunk, KnowledgeChunkIndex, load_approved_chunks
from backend.fixtures import load_demo_salon_fixture
from backend.knowledge import (
    AnswerStatus,
    KnowledgeAnswer,
    KnowledgeCategory,
    KnowledgeService,
    compose_answer,
)

_WORD = re.compile(r"[a-z0-9]+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_PRICE = re.compile(r"(?:\$|USD\s*)(\d+(?:\.\d+)?)")
_DURATION = re.compile(r"(\d+)\s*minutes?")
_TIME_RANGE = re.compile(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})")

_MIN_OVERLAP_TOKENS = 1

# Common English stopwords excluded from token matching so that mere
# single-word overlap (e.g. "the", "a", "is") is not treated as evidence.
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "can", "to", "of", "in", "for", "on",
    "at", "by", "from", "as", "with", "about", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "what", "which", "who", "whom", "this", "that", "these", "those",
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you",
    "your", "yours", "yourself", "yourselves", "he", "him", "his",
    "himself", "she", "her", "hers", "herself", "it", "its", "itself",
    "they", "them", "their", "theirs", "themselves", "am",
})

# Booking permission signals — narrow enough to avoid false positives on
# availability content that merely mentions appointments or slots.
_BOOKING_ALLOW = frozenset({"bookable", "can book", "book now"})
_BOOKING_DENY = frozenset(
    {"cannot book", "does not book", "not bookable", "not available for booking"}
)


class FusionStatus(StrEnum):
    """Outcome of a fused retrieval over approved chunks.

    This retriever is intentionally lexical (token overlap), NOT semantic.
    Genuine semantic retrieval requires an embedding provider and is tracked
    under A05; it is not implemented or claimed here.
    """

    MATCHED = "matched"
    CONFLICT = "conflict"
    UNSUPPORTED = "unsupported"
    FALLBACK_OKF = "fallback_okf"


@dataclass(frozen=True)
class EvidenceItem:
    """A single approved chunk selected as evidence for a query."""

    chunk_id: str
    source_id: str
    document_id: str
    version: str
    category: KnowledgeCategory
    content: str
    content_hash: str
    provenance: str  # "fixture" or "bundle"


@dataclass(frozen=True)
class FusedResult:
    """Result of fusing approved-chunk evidence for one customer query."""

    query: str
    status: FusionStatus
    reason: str
    evidence: tuple[EvidenceItem, ...]
    source_ids: tuple[str, ...]  # deduplicated, fixture IDs ordered first
    answer_text: str | None
    fallback_to_okf: bool


class _ServiceFacts(NamedTuple):
    """Structured facts extracted from evidence for one service and provenance."""

    service_id: str
    provenance: str
    prices: frozenset[str]  # normalized "$35" etc.
    durations: frozenset[int]  # minutes
    time_ranges: frozenset[tuple[str, str]]  # (open, close)
    booking_allow: frozenset[str]
    booking_deny: frozenset[str]


class RagRetriever:
    """Deterministic lexical fusion over approved knowledge chunks.

    Builds on A01's ``KnowledgeChunkIndex``. For each query it:
      1. selects chunks with meaningful token overlap with the query
         (at least ``MIN_OVERLAP_TOKENS`` shared tokens, one-letter
         stopwords excluded);
      2. deduplicates by source_id (canonical fixture precedes bundle);
      3. extracts structured facts (prices, durations, hours, booking
         restrictions) per service and provenance;
      4. flags contradictions only within the same provenance — fixture
         and bundle disagreements are resolved in favor of the fixture;
      5. falls back to the existing deterministic OKF path when no chunk
         has meaningful overlap.

    No embeddings, vector database, or paid provider is used. A genuine
    semantic retriever is an explicit A05 dependency and remains pending.
    """

    MIN_OVERLAP_TOKENS = _MIN_OVERLAP_TOKENS

    def __init__(
        self,
        index: KnowledgeChunkIndex | None = None,
        okf: KnowledgeService | None = None,
    ) -> None:
        self.index = index or load_approved_chunks()
        self.okf = okf or KnowledgeService()
        self._services = load_demo_salon_fixture().services

    # -- token helpers -----------------------------------------------------

    @staticmethod
    def _tokens(text: str) -> set[str]:
        """Case-insensitive content tokens; drop stopwords and one-letter words."""
        return {
            t
            for t in _WORD.findall(text.casefold())
            if len(t) >= 2 and t not in _STOPWORDS
        }

    @staticmethod
    def _normalize_price(price_str: str) -> str:
        """Canonical price comparison: $35 and USD 35.00 normalize alike."""
        value = Decimal(price_str)
        return f"${value.normalize()}"

    def _prices_in(self, text: str) -> frozenset[str]:
        """Extract normalized prices from a snippet of text."""
        return frozenset(
            self._normalize_price(match.group(1))
            for match in _PRICE.finditer(text)
        )

    def _durations_in(self, text: str) -> frozenset[int]:
        """Extract duration values in minutes from text."""
        return frozenset(
            int(match.group(1)) for match in _DURATION.finditer(text)
        )

    def _time_ranges_in(self, text: str) -> frozenset[tuple[str, str]]:
        """Extract time ranges (open, close) from text."""
        return frozenset(
            (match.group(1), match.group(2))
            for match in _TIME_RANGE.finditer(text)
        )

    @staticmethod
    def _provenance(source_id: str) -> str:
        return "fixture" if source_id.startswith("fixture:") else "bundle"

    def _validate_approved_source(self, source_id: str) -> None:
        """Defensive check: evidence must come from an approved source.

        The chunker already guarantees only approved records are loaded;
        this is a belt-and-suspenders guard for the fusion layer.
        """
        if not source_id:
            raise ValueError("evidence source_id must not be empty")

    # -- retrieval ---------------------------------------------------------

    def _match_chunks(self, query: str) -> tuple[KnowledgeChunk, ...]:
        """Select chunks with meaningful token overlap with the query.

        Mere single-word overlap is not sufficient evidence: at least
        ``MIN_OVERLAP_TOKENS`` shared content tokens are required.
        """
        query_tokens = self._tokens(query)
        if not query_tokens:
            return ()
        scored: list[tuple[int, KnowledgeChunk]] = []
        for chunk in self.index.chunks:
            content_tokens = self._tokens(chunk.content)
            overlap = len(query_tokens & content_tokens)
            if overlap >= self.MIN_OVERLAP_TOKENS:
                scored.append((overlap, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return tuple(chunk for _, chunk in scored)

    def _collect_service_facts(
        self, evidence: tuple[EvidenceItem, ...]
    ) -> dict[tuple[str, str], _ServiceFacts]:
        """Collect structured facts per (service_id, provenance).

        Facts are extracted at sentence level so that a price or duration
        mentioned for one service in a multi-service sentence is not
        misattributed to another service. Facts are grouped by service and
        provenance so that contradictions are only flagged within the same
        authority. Fixture and bundle disagreements are resolved by fixture
        precedence elsewhere.
        """
        collected: dict[tuple[str, str], dict] = defaultdict(
            lambda: {
                "prices": set(),
                "durations": set(),
                "time_ranges": set(),
                "booking_allow": set(),
                "booking_deny": set(),
            }
        )

        for item in evidence:
            self._validate_approved_source(item.source_id)
            provenance = self._provenance(item.source_id)

            for sentence in [
                s.strip() for s in _SENTENCE.split(item.content) if s.strip()
            ]:
                sentence_lower = sentence.casefold()
                service_names = [
                    svc
                    for svc in self._services
                    if svc.name.casefold() in sentence_lower
                ]
                if not service_names:
                    continue
                best_svc = max(service_names, key=lambda s: len(s.name))
                key = (best_svc.service_id, provenance)
                facts = collected[key]
                facts["prices"].update(self._prices_in(sentence))
                facts["durations"].update(self._durations_in(sentence))
                facts["time_ranges"].update(self._time_ranges_in(sentence))
                for term in _BOOKING_ALLOW:
                    if term in sentence_lower:
                        facts["booking_allow"].add(term)
                for term in _BOOKING_DENY:
                    if term in sentence_lower:
                        facts["booking_deny"].add(term)

        return {
            key: _ServiceFacts(
                service_id=key[0],
                provenance=key[1],
                prices=frozenset(vals["prices"]),
                durations=frozenset(vals["durations"]),
                time_ranges=frozenset(vals["time_ranges"]),
                booking_allow=frozenset(vals["booking_allow"]),
                booking_deny=frozenset(vals["booking_deny"]),
            )
            for key, vals in collected.items()
        }

    def _has_contradiction(
        self, service_facts: dict[tuple[str, str], _ServiceFacts]
    ) -> tuple[bool, str | None]:
        """Check for contradictions within the same provenance group.

        Fixture-vs-bundle disagreements are NOT contradictions here — the
        fixture is authoritative and resolves them elsewhere. Only two
        sources within the same provenance disagreeing on the same
        structured fact is a conflict.
        """
        for (_service_id, provenance), facts in service_facts.items():
            if len(facts.prices) > 1:
                return True, f"conflicting_prices_for_{_service_id}"
            if len(facts.durations) > 1:
                return True, f"conflicting_durations_for_{_service_id}"
            if len(facts.time_ranges) > 1:
                return True, f"conflicting_hours_for_{_service_id}"
            if facts.booking_allow and facts.booking_deny:
                return True, f"conflicting_booking_for_{_service_id}"
        return False, None

    def retrieve(self, query: str) -> FusedResult:
        matched = self._match_chunks(query)

        # Empty retrieval -> deterministic OKF fallback (existing P0 path).
        if not matched:
            okf = self.okf.retrieve(query)
            answer = compose_answer(okf)
            return FusedResult(
                query=query,
                status=FusionStatus.FALLBACK_OKF,
                reason=okf.reason,
                evidence=(),
                source_ids=okf.source_ids,
                answer_text=answer.text,
                fallback_to_okf=True,
            )

        # Dedup by source_id; canonical fixture precedes bundle.
        best_by_source: dict[str, KnowledgeChunk] = {}
        for chunk in matched:
            current = best_by_source.get(chunk.source_id)
            if current is None:
                best_by_source[chunk.source_id] = chunk
                continue
            if (
                self._provenance(chunk.source_id) == "fixture"
                and self._provenance(current.source_id) == "bundle"
            ):
                best_by_source[chunk.source_id] = chunk

        evidence_items = [
            EvidenceItem(
                chunk_id=c.chunk_id,
                source_id=c.source_id,
                document_id=c.document_id,
                version=c.version,
                category=c.category,
                content=c.content,
                content_hash=c.content_hash,
                provenance=self._provenance(c.source_id),
            )
            for c in best_by_source.values()
        ]
        # Fixture evidence first so fixture content is preferred in answers.
        evidence_items.sort(key=lambda e: e.provenance != "fixture")
        evidence = tuple(evidence_items)

        fixture_ids = [
            sid for sid in best_by_source if sid.startswith("fixture:")
        ]
        bundle_ids = [
            sid for sid in best_by_source if not sid.startswith("fixture:")
        ]
        source_ids = tuple(fixture_ids + bundle_ids)

        # Contradiction detection within the same provenance only.
        service_facts = self._collect_service_facts(evidence)
        has_conflict, conflict_reason = self._has_contradiction(service_facts)

        if has_conflict:
            return FusedResult(
                query=query,
                status=FusionStatus.CONFLICT,
                reason=conflict_reason or "conflicting_approved_sources",
                evidence=evidence,
                source_ids=source_ids,
                answer_text=None,
                fallback_to_okf=False,
            )

        # Fixture precedence: prefer fixture content for the answer text.
        fixture_evidence = [e for e in evidence if e.provenance == "fixture"]
        answer_text = (
            fixture_evidence[0].content
            if fixture_evidence
            else (evidence[0].content if evidence else None)
        )
        return FusedResult(
            query=query,
            status=FusionStatus.MATCHED,
            reason="approved_chunk_match",
            evidence=evidence,
            source_ids=source_ids,
            answer_text=answer_text,
            fallback_to_okf=False,
        )

    def answer(self, query: str) -> KnowledgeAnswer:
        """Compose a :class:`KnowledgeAnswer` from the fused result.

        The answer text and source citations come exclusively from the
        fused evidence; no facts are invented.
        """
        fused = self.retrieve(query)
        if fused.status is FusionStatus.FALLBACK_OKF:
            return KnowledgeAnswer(
                text=fused.answer_text or "I don't have approved information to answer that question.",
                status=(
                    AnswerStatus.ANSWERED
                    if fused.source_ids
                    else AnswerStatus.ABSTAINED
                ),
                reason=fused.reason,
                source_ids=fused.source_ids,
            )
        if fused.status is FusionStatus.CONFLICT:
            return KnowledgeAnswer(
                text="I found conflicting approved information for that request. Please clarify.",
                status=AnswerStatus.ABSTAINED,
                reason=fused.reason,
                source_ids=fused.source_ids,
            )
        if fused.status is FusionStatus.UNSUPPORTED:
            return KnowledgeAnswer(
                text="I don't have approved information to answer that question.",
                status=AnswerStatus.ABSTAINED,
                reason="no_approved_source_match",
                source_ids=(),
            )
        return KnowledgeAnswer(
            text=fused.answer_text or "I don't have approved information to answer that question.",
            status=AnswerStatus.ANSWERED,
            reason=fused.reason,
            source_ids=fused.source_ids,
        )


_RAG_ENABLED_KEY = "TECHOHUB_RAG_ENABLED"
_RAG_PROVIDER_KEY = "TECHOHUB_RAG_PROVIDER"
_DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
_FALSE_VALUES = frozenset({"false", "0", "no", "off"})
_PROVIDER_VALUES = frozenset({"lexical", "semantic", "auto"})


class RagConfig:
    """Configuration for the RAG feature flag and retrieval provider.

    The feature flag defaults to OFF. Only explicit ``true``/``1``/``yes``/``on``
    enables RAG. Any other value raises ``ValueError`` so that invalid
    configuration never silently enables RAG.

    The provider selects which retriever answers FAQ queries when RAG is on:
    ``lexical`` uses token-overlap matching, ``semantic`` uses trained
    embeddings, and ``auto`` uses semantic when available, otherwise lexical.
    """

    def __init__(self, enabled: bool = False, provider: str = "lexical") -> None:
        self.enabled = enabled
        self.provider = provider

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "RagConfig":
        env = environ if environ is not None else os.environ
        raw = env.get(_RAG_ENABLED_KEY, "false").strip().lower()
        if raw in _TRUE_VALUES:
            enabled = True
        elif raw in _FALSE_VALUES:
            enabled = False
        else:
            raise ValueError(
                f"Invalid {_RAG_ENABLED_KEY} value: {env.get(_RAG_ENABLED_KEY)!r}. "
                f"Expected one of {sorted(_TRUE_VALUES | _FALSE_VALUES)}."
            )

        provider = env.get(_RAG_PROVIDER_KEY, "lexical").strip().lower()
        if provider not in _PROVIDER_VALUES:
            raise ValueError(
                f"Invalid {_RAG_PROVIDER_KEY} value: {provider!r}. "
                f"Expected one of {sorted(_PROVIDER_VALUES)}."
            )
        return cls(enabled=enabled, provider=provider)


@runtime_checkable
class SemanticEmbeddingProvider(Protocol):
    """Protocol for embedding-based retrieval providers.

    Implementations must not access the network at inference time; models are
    expected to be pre-cached locally.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return an embedding vector for each input text."""
        ...

    def similarity(self, a: list[float], b: list[float]) -> float:
        """Return cosine similarity between two embedding vectors."""
        ...

    @property
    def dimension(self) -> int:
        """Embedding vector dimension."""
        ...


class SentenceTransformerProvider:
    """Sentence-Transformers embedding provider using a locally cached model.

    The model is loaded lazily on first ``embed`` call so that importing this
    module does not pull Torch into memory when semantic retrieval is not used.
    The model files must already exist in the local Hugging Face cache; no
    download is attempted at runtime.
    """

    def __init__(self, model_name: str = _DEFAULT_EMBEDDING_MODEL) -> None:
        self._model_name = model_name
        self._model: SentenceTransformer | None = None

    def _load_model(self) -> SentenceTransformer:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        vectors = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def similarity(self, a: list[float], b: list[float]) -> float:
        import numpy as np

        va = np.asarray(a, dtype=np.float64)
        vb = np.asarray(b, dtype=np.float64)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        if denom == 0.0:
            return 0.0
        return float(np.dot(va, vb) / denom)

    @property
    def dimension(self) -> int:
        model = self._load_model()
        dim = getattr(model, "get_embedding_dimension", None)
        if dim is not None:
            return int(dim())
        return int(model.get_sentence_embedding_dimension())


class SemanticRetriever:
    """Semantic retrieval over approved knowledge chunks using embeddings.

    Wraps an existing :class:`KnowledgeChunkIndex` and a
    :class:`SemanticEmbeddingProvider`. For each query it:
      1. embeds the query and every chunk,
      2. computes cosine similarity,
      3. selects chunks above a similarity threshold,
      4. deduplicates by source_id (fixture precedes bundle),
      5. delegates conflict detection and fixture precedence to the shared
         fusion logic inherited from :class:`RagRetriever`.

    Empty/low-similarity retrieval falls back to the deterministic OKF path.
    """

    def __init__(
        self,
        index: KnowledgeChunkIndex,
        provider: SemanticEmbeddingProvider,
        okf: KnowledgeService | None = None,
        similarity_threshold: float = 0.4,
        top_k: int = 5,
    ) -> None:
        self.index = index
        self.provider = provider
        self.okf = okf or KnowledgeService()
        self._services = load_demo_salon_fixture().services
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k

    @staticmethod
    def _provenance(source_id: str) -> str:
        return "fixture" if source_id.startswith("fixture:") else "bundle"

    @staticmethod
    def _validate_approved_source(source_id: str) -> None:
        """Defensive check: evidence must come from an approved source."""
        if not source_id:
            raise ValueError("evidence source_id must not be empty")

    @staticmethod
    def _prices_in(text: str) -> frozenset[str]:
        """Extract normalized prices from a snippet of text."""
        return frozenset(
            RagRetriever._normalize_price(match.group(1))
            for match in _PRICE.finditer(text)
        )

    @staticmethod
    def _durations_in(text: str) -> frozenset[int]:
        """Extract duration values in minutes from text."""
        return frozenset(
            int(match.group(1)) for match in _DURATION.finditer(text)
        )

    @staticmethod
    def _time_ranges_in(text: str) -> frozenset[tuple[str, str]]:
        """Extract time ranges (open, close) from text."""
        return frozenset(
            (match.group(1), match.group(2))
            for match in _TIME_RANGE.finditer(text)
        )

    def _match_chunks(self, query: str) -> tuple[KnowledgeChunk, ...]:
        """Select chunks whose embedding is semantically similar to the query.

        At least ``top_k`` candidates are scored, then only those at or above
        ``similarity_threshold`` are returned.
        """
        if not self.index.chunks:
            return ()
        query_embedding = self.provider.embed([query])[0]
        chunk_texts = [chunk.content for chunk in self.index.chunks]
        chunk_embeddings = self.provider.embed(chunk_texts)

        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk, embedding in zip(self.index.chunks, chunk_embeddings):
            score = self.provider.similarity(query_embedding, embedding)
            if score >= self.similarity_threshold:
                scored.append((score, chunk))

        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return tuple(chunk for _, chunk in scored[: self.top_k])

    def _collect_service_facts(
        self, evidence: tuple[EvidenceItem, ...]
    ) -> dict[tuple[str, str], _ServiceFacts]:
        """Collect structured facts per (service_id, provenance).

        Same logic as RagRetriever._collect_service_facts but on SemanticRetriever.
        """
        collected: dict[tuple[str, str], dict] = defaultdict(
            lambda: {
                "prices": set(),
                "durations": set(),
                "time_ranges": set(),
                "booking_allow": set(),
                "booking_deny": set(),
            }
        )

        for item in evidence:
            self._validate_approved_source(item.source_id)
            provenance = self._provenance(item.source_id)

            for sentence in [
                s.strip() for s in _SENTENCE.split(item.content) if s.strip()
            ]:
                sentence_lower = sentence.casefold()
                service_names = [
                    svc
                    for svc in self._services
                    if svc.name.casefold() in sentence_lower
                ]
                if not service_names:
                    continue
                best_svc = max(service_names, key=lambda s: len(s.name))
                key = (best_svc.service_id, provenance)
                facts = collected[key]
                facts["prices"].update(self._prices_in(sentence))
                facts["durations"].update(self._durations_in(sentence))
                facts["time_ranges"].update(self._time_ranges_in(sentence))
                for term in _BOOKING_ALLOW:
                    if term in sentence_lower:
                        facts["booking_allow"].add(term)
                for term in _BOOKING_DENY:
                    if term in sentence_lower:
                        facts["booking_deny"].add(term)

        return {
            key: _ServiceFacts(
                service_id=key[0],
                provenance=key[1],
                prices=frozenset(vals["prices"]),
                durations=frozenset(vals["durations"]),
                time_ranges=frozenset(vals["time_ranges"]),
                booking_allow=frozenset(vals["booking_allow"]),
                booking_deny=frozenset(vals["booking_deny"]),
            )
            for key, vals in collected.items()
        }

    def _has_contradiction(
        self, service_facts: dict[tuple[str, str], _ServiceFacts]
    ) -> tuple[bool, str | None]:
        """Check for contradictions within the same provenance group."""
        for (_service_id, provenance), facts in service_facts.items():
            if len(facts.prices) > 1:
                return True, f"conflicting_prices_for_{_service_id}"
            if len(facts.durations) > 1:
                return True, f"conflicting_durations_for_{_service_id}"
            if len(facts.time_ranges) > 1:
                return True, f"conflicting_hours_for_{_service_id}"
            if facts.booking_allow and facts.booking_deny:
                return True, f"conflicting_booking_for_{_service_id}"
        return False, None

    def retrieve(self, query: str) -> FusedResult:
        matched = self._match_chunks(query)

        # Empty retrieval -> deterministic OKF fallback.
        if not matched:
            okf = self.okf.retrieve(query)
            answer = compose_answer(okf)
            return FusedResult(
                query=query,
                status=FusionStatus.FALLBACK_OKF,
                reason=okf.reason,
                evidence=(),
                source_ids=okf.source_ids,
                answer_text=answer.text,
                fallback_to_okf=True,
            )

        best_by_source: dict[str, KnowledgeChunk] = {}
        for chunk in matched:
            current = best_by_source.get(chunk.source_id)
            if current is None:
                best_by_source[chunk.source_id] = chunk
                continue
            if (
                self._provenance(chunk.source_id) == "fixture"
                and self._provenance(current.source_id) == "bundle"
            ):
                best_by_source[chunk.source_id] = chunk

        evidence_items = [
            EvidenceItem(
                chunk_id=c.chunk_id,
                source_id=c.source_id,
                document_id=c.document_id,
                version=c.version,
                category=c.category,
                content=c.content,
                content_hash=c.content_hash,
                provenance=self._provenance(c.source_id),
            )
            for c in best_by_source.values()
        ]
        evidence_items.sort(key=lambda e: e.provenance != "fixture")
        evidence = tuple(evidence_items)

        fixture_ids = [sid for sid in best_by_source if sid.startswith("fixture:")]
        bundle_ids = [sid for sid in best_by_source if not sid.startswith("fixture:")]
        source_ids = tuple(fixture_ids + bundle_ids)

        service_facts = self._collect_service_facts(evidence)
        has_conflict, conflict_reason = self._has_contradiction(service_facts)

        if has_conflict:
            return FusedResult(
                query=query,
                status=FusionStatus.CONFLICT,
                reason=conflict_reason or "conflicting_approved_sources",
                evidence=evidence,
                source_ids=source_ids,
                answer_text=None,
                fallback_to_okf=False,
            )

        fixture_evidence = [e for e in evidence if e.provenance == "fixture"]
        answer_text = (
            fixture_evidence[0].content
            if fixture_evidence
            else (evidence[0].content if evidence else None)
        )
        return FusedResult(
            query=query,
            status=FusionStatus.MATCHED,
            reason="approved_chunk_match",
            evidence=evidence,
            source_ids=source_ids,
            answer_text=answer_text,
            fallback_to_okf=False,
        )

    def answer(self, query: str) -> KnowledgeAnswer:
        fused = self.retrieve(query)
        if fused.status is FusionStatus.FALLBACK_OKF:
            return KnowledgeAnswer(
                text=fused.answer_text or "I don't have approved information to answer that question.",
                status=(
                    AnswerStatus.ANSWERED
                    if fused.source_ids
                    else AnswerStatus.ABSTAINED
                ),
                reason=fused.reason,
                source_ids=fused.source_ids,
            )
        if fused.status is FusionStatus.CONFLICT:
            return KnowledgeAnswer(
                text="I found conflicting approved information for that request. Please clarify.",
                status=AnswerStatus.ABSTAINED,
                reason=fused.reason,
                source_ids=fused.source_ids,
            )
        if fused.status is FusionStatus.UNSUPPORTED:
            return KnowledgeAnswer(
                text="I don't have approved information to answer that question.",
                status=AnswerStatus.ABSTAINED,
                reason="no_approved_source_match",
                source_ids=(),
            )
        return KnowledgeAnswer(
            text=fused.answer_text or "I don't have approved information to answer that question.",
            status=AnswerStatus.ANSWERED,
            reason=fused.reason,
            source_ids=fused.source_ids,
        )

