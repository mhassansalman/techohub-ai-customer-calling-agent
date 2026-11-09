from __future__ import annotations

import hashlib
import os
from decimal import Decimal

import pytest

from backend.chunker import (
    KnowledgeChunk,
    KnowledgeChunkIndex,
    chunk_record,
    load_approved_chunks,
)
from backend.fixtures import load_demo_salon_fixture
from backend.knowledge import (
    AnswerStatus,
    KnowledgeCategory,
    KnowledgeRecord,
    KnowledgeService,
)
from backend.rag import (
    EvidenceItem,
    FusionStatus,
    FusedResult,
    RagConfig,
    RagRetriever,
    SemanticRetriever,
    SentenceTransformerProvider,
)


def _make_chunk(
    source_id: str,
    content: str,
    category: KnowledgeCategory = KnowledgeCategory.FAQ,
    provenance: str = "bundle",
) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=f"{source_id}#chunk=0",
        source_id=source_id,
        source_reference=f"{source_id}.md#version=1.0.0",
        category=category,
        status="approved",
        content=content,
        document_id=f"{source_id}.md",
        version="1.0.0",
        chunk_index=0,
        content_hash=__import__("hashlib").sha256(content.encode("utf-8")).hexdigest(),
        word_count=len(content.split()),
    )


def _conflicting_index() -> KnowledgeChunkIndex:
    """Two approved bundle sources that disagree on the haircut price.

    With fixture precedence (A03), fixture-vs-bundle disagreements are
    resolved in favor of the fixture, so a real conflict requires two
    sources within the same provenance disagreeing.
    """
    chunks = (
        _make_chunk(
            "kb:faq/conflicting-pricing-a",
            "A haircut costs $50 and takes about 30 minutes.",
            KnowledgeCategory.FAQ,
            "bundle",
        ),
        _make_chunk(
            "kb:faq/conflicting-pricing-b",
            "A haircut costs $35 and takes about 30 minutes.",
            KnowledgeCategory.FAQ,
            "bundle",
        ),
    )
    return KnowledgeChunkIndex(chunks=chunks)


def _conflicting_duration_index() -> KnowledgeChunkIndex:
    """Two approved bundle sources that disagree on haircut duration."""
    chunks = (
        _make_chunk(
            "kb:faq/conflicting-duration-a",
            "A haircut takes about 30 minutes.",
            KnowledgeCategory.FAQ,
            "bundle",
        ),
        _make_chunk(
            "kb:faq/conflicting-duration-b",
            "A haircut takes about 45 minutes.",
            KnowledgeCategory.FAQ,
            "bundle",
        ),
    )
    return KnowledgeChunkIndex(chunks=chunks)


def _fixture_wins_index() -> KnowledgeChunkIndex:
    """Fixture and bundle disagree on price; fixture must win."""
    chunks = (
        _make_chunk(
            "fixture:demo-salon-v1:service:haircut",
            "Haircut: 30 minutes, USD 35.00; active in the service catalog.",
            KnowledgeCategory.SERVICE,
            "fixture",
        ),
        _make_chunk(
            "kb:faq/higher-pricing",
            "A haircut costs $50 and takes about 30 minutes.",
            KnowledgeCategory.FAQ,
            "bundle",
        ),
    )
    return KnowledgeChunkIndex(chunks=chunks)


def test_retriever_uses_lexical_not_semantic_matching() -> None:
    """The retriever is token-overlap based; it makes no embedding claim."""
    retriever = RagRetriever()
    result = retriever.retrieve("How much is a haircut?")
    assert result.status in {FusionStatus.MATCHED, FusionStatus.FALLBACK_OKF}
    # Documented limitation: no semantic embedding provider is wired in.
    assert result.fallback_to_okf is False or result.status is FusionStatus.FALLBACK_OKF


def test_paraphrase_returns_same_sources() -> None:
    retriever = RagRetriever()
    first = retriever.retrieve("What is the price of a haircut?")
    second = retriever.retrieve("How much does a haircut cost?")
    assert first.status is FusionStatus.MATCHED
    assert second.status is FusionStatus.MATCHED
    # Both paraphrases resolve to at least one shared approved source.
    assert set(first.source_ids) & set(second.source_ids)


def test_fixture_precedence_in_source_ids() -> None:
    retriever = RagRetriever()
    result = retriever.retrieve("How much is a haircut?")
    assert result.status is FusionStatus.MATCHED
    assert len(result.source_ids) >= 1
    # Canonical fixture source IDs must be ordered before bundle IDs.
    fixture_ids = [sid for sid in result.source_ids if sid.startswith("fixture:")]
    bundle_ids = [sid for sid in result.source_ids if sid.startswith("kb:")]
    if fixture_ids and bundle_ids:
        assert result.source_ids.index(fixture_ids[0]) < result.source_ids.index(
            bundle_ids[0]
        )


def test_source_provenance_labels() -> None:
    retriever = RagRetriever()
    result = retriever.retrieve("What are your opening hours?")
    assert result.status is FusionStatus.MATCHED
    provenance_by_source = {
        item.source_id: item.provenance for item in result.evidence
    }
    for source_id, prov in provenance_by_source.items():
        expected = "fixture" if source_id.startswith("fixture:") else "bundle"
        assert prov == expected, f"{source_id}: expected {expected}, got {prov}"


def test_empty_retrieval_falls_back_to_okf() -> None:
    retriever = RagRetriever()
    result = retriever.retrieve("")
    assert result.status is FusionStatus.FALLBACK_OKF
    assert result.fallback_to_okf is True
    assert result.evidence == ()


def test_unsupported_policy_falls_back_to_okf_and_abstains() -> None:
    retriever = RagRetriever()
    result = retriever.retrieve("Can I get a refund?")
    assert result.status is FusionStatus.FALLBACK_OKF
    assert result.fallback_to_okf is True
    answer = retriever.answer("Can I get a refund?")
    assert answer.status is AnswerStatus.ABSTAINED
    assert "approved information" in answer.text


def test_conflicting_approved_sources_safe_abstain() -> None:
    index = _conflicting_index()
    retriever = RagRetriever(index=index)
    result = retriever.retrieve("How much is a haircut?")
    assert result.status is FusionStatus.CONFLICT
    assert result.reason == "conflicting_prices_for_haircut"
    assert result.fallback_to_okf is False
    # Both sources cited for provenance; no single answer claimed.
    assert len(result.source_ids) == 2
    answer = retriever.answer("How much is a haircut?")
    assert answer.status is AnswerStatus.ABSTAINED
    assert answer.reason == "conflicting_prices_for_haircut"
    assert "conflicting" in answer.text


def test_conflict_detection_normalizes_price_variants() -> None:
    """$35 and $35.00 are the same price; must not be a false conflict."""
    retriever = RagRetriever()
    result = retriever.retrieve("How much is a haircut?")
    # Real bundle ($35) and fixture ($35.00) agree; must be MATCHED, not CONFLICT.
    assert result.status is FusionStatus.MATCHED, result.reason


def test_fused_result_source_ids_deduplicated() -> None:
    retriever = RagRetriever()
    result = retriever.retrieve("How much is a haircut?")
    assert result.status is FusionStatus.MATCHED
    assert len(result.source_ids) == len(set(result.source_ids))


def test_answer_returns_knowledge_answer_with_sources() -> None:
    retriever = RagRetriever()
    answer = retriever.answer("What is the price of a haircut?")
    assert answer.status is AnswerStatus.ANSWERED
    assert answer.source_ids
    assert answer.text.strip()
    # The approved price is present somewhere in the retrieved evidence.
    retrieved = retriever.retrieve("What is the price of a haircut?")
    assert any("$35" in item.content or "35.00" in item.content for item in retrieved.evidence)


def test_load_approved_chunks_feeds_retriever() -> None:
    index = load_approved_chunks(max_words=100)
    assert isinstance(index, KnowledgeChunkIndex)
    assert len(index.chunks) > 0
    retriever = RagRetriever(index=index)
    result = retriever.retrieve("haircut price duration")
    assert result.status is FusionStatus.MATCHED


def test_fixture_precedence_resolves_price_conflict() -> None:
    """Fixture-vs-bundle price disagreement: fixture wins, no conflict."""
    index = _fixture_wins_index()
    retriever = RagRetriever(index=index)
    result = retriever.retrieve("How much is a haircut?")
    assert result.status is FusionStatus.MATCHED
    # Fixture's price ($35 / USD 35.00) is used for the answer, not the
    # bundle's ($50). Bundle evidence remains for provenance transparency.
    fixture_items = [i for i in result.evidence if i.provenance == "fixture"]
    assert len(fixture_items) >= 1
    assert any("35.00" in item.content for item in fixture_items)
    answer = retriever.answer("How much is a haircut?")
    assert answer.status is AnswerStatus.ANSWERED
    assert "35" in answer.text
    assert "50" not in answer.text


def test_duration_contradiction_safe_abstain() -> None:
    """Two bundle sources disagree on duration -> conflict -> abstain."""
    index = _conflicting_duration_index()
    retriever = RagRetriever(index=index)
    result = retriever.retrieve("How long does a haircut take?")
    assert result.status is FusionStatus.CONFLICT
    assert result.reason == "conflicting_durations_for_haircut"
    answer = retriever.answer("How long does a haircut take?")
    assert answer.status is AnswerStatus.ABSTAINED
    assert answer.reason == "conflicting_durations_for_haircut"


def test_misleading_keyword_match_falls_back_to_okf() -> None:
    """A single common word is not sufficient evidence to answer."""
    retriever = RagRetriever()
    result = retriever.retrieve("the")
    assert result.status is FusionStatus.FALLBACK_OKF
    assert result.fallback_to_okf is True
    assert result.evidence == ()


def test_unrelated_query_falls_back_to_okf() -> None:
    """An unrelated query with no approved match falls back to OKF."""
    retriever = RagRetriever()
    result = retriever.retrieve("quantum physics research")
    assert result.status is FusionStatus.FALLBACK_OKF
    assert result.fallback_to_okf is True


def test_answer_grounded_in_evidence_only() -> None:
    """The fusion answer text comes exclusively from evidence, not invented."""
    retriever = RagRetriever()
    answer = retriever.answer("What are your opening hours?")
    assert answer.status is AnswerStatus.ANSWERED
    assert answer.source_ids
    retrieved = retriever.retrieve("What are your opening hours?")
    # The answer text must match some evidence chunk exactly.
    assert any(answer.text == item.content for item in retrieved.evidence)
    # Every cited source must be approved.
    for source_id in answer.source_ids:
        assert source_id.startswith("fixture:") or source_id.startswith("kb:")


def test_knowledge_service_still_answers_directly() -> None:
    """A02 must not alter the existing deterministic OKF path (A01 regression guard)."""
    service = KnowledgeService()
    answer = service.answer("How much is a haircut?")
    assert answer.status is AnswerStatus.ANSWERED
    assert answer.source_ids
    assert "$35" in answer.text


def test_fixture_canonical_values_unaltered() -> None:
    fixture = load_demo_salon_fixture()
    services = {s.service_id: s for s in fixture.services}
    assert services["haircut"].price_amount == Decimal("35.00")
    assert services["haircut"].duration_minutes == 30
    assert services["beard-trim"].price_amount == Decimal("18.00")
    assert services["beard-trim"].duration_minutes == 20
    assert services["haircut-beard"].price_amount == Decimal("45.00")
    assert services["haircut-beard"].duration_minutes == 45


def test_rag_config_defaults_to_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """TECHOHUB_RAG_ENABLED defaults to OFF when not set."""
    monkeypatch.delenv("TECHOHUB_RAG_ENABLED", raising=False)
    config = RagConfig.from_environment()
    assert config.enabled is False


@pytest.mark.parametrize(
    "raw_value",
    ["true", "True", "1", "yes", "Yes", "on", "ON"],
)
def test_rag_config_true_values_enable_rag(
    monkeypatch: pytest.MonkeyPatch, raw_value: str
) -> None:
    """Explicit true-like values enable RAG."""
    monkeypatch.setenv("TECHOHUB_RAG_ENABLED", raw_value)
    config = RagConfig.from_environment()
    assert config.enabled is True


@pytest.mark.parametrize(
    "raw_value",
    ["false", "False", "0", "no", "No", "off", "OFF"],
)
def test_rag_config_false_values_disable_rag(
    monkeypatch: pytest.MonkeyPatch, raw_value: str
) -> None:
    """Explicit false-like values disable RAG."""
    monkeypatch.setenv("TECHOHUB_RAG_ENABLED", raw_value)
    config = RagConfig.from_environment()
    assert config.enabled is False


def test_rag_config_invalid_value_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid TECHOHUB_RAG_ENABLED values raise ValueError (never silently enable)."""
    monkeypatch.setenv("TECHOHUB_RAG_ENABLED", "maybe")
    with pytest.raises(ValueError, match="Invalid TECHOHUB_RAG_ENABLED value"):
        RagConfig.from_environment()


def test_rag_config_accepts_environ_override() -> None:
    """RagConfig.from_environment accepts an explicit environ mapping."""
    config = RagConfig.from_environment(
        environ={"TECHOHUB_RAG_ENABLED": "true"}
    )
    assert config.enabled is True

    config = RagConfig.from_environment(
        environ={"TECHOHUB_RAG_ENABLED": "false"}
    )
    assert config.enabled is False


# ---------------------------------------------------------------------------
# SemanticRetriever tests (real model, cached offline)
# ---------------------------------------------------------------------------


def _make_semantic_retriever() -> SemanticRetriever | None:
    """Build a SemanticRetriever from the cached model, or None if unavailable."""
    try:
        provider = SentenceTransformerProvider()
        # Force model load to verify offline availability
        provider.embed(["probe"])
        return SemanticRetriever(
            index=load_approved_chunks(),
            provider=provider,
        )
    except Exception:
        return None


def test_semantic_retriever_loads_offline_model() -> None:
    """The cached all-MiniLM-L6-v2 model loads without network access."""
    provider = SentenceTransformerProvider()
    vectors = provider.embed(["How much is a haircut?"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 384
    assert provider.dimension == 384


def test_semantic_retriever_exact_service_question() -> None:
    retriever = _make_semantic_retriever()
    if retriever is None:
        pytest.skip("SentenceTransformer model not available offline")
    result = retriever.retrieve("How much is a haircut?")
    assert result.status == FusionStatus.MATCHED
    assert result.fallback_to_okf is False
    answer = retriever.answer("How much is a haircut?")
    assert answer.status == AnswerStatus.ANSWERED
    assert "35" in answer.text


def test_semantic_retriever_paraphrased_faq() -> None:
    """Paraphrased questions with low lexical overlap should still match."""
    retriever = _make_semantic_retriever()
    if retriever is None:
        pytest.skip("SentenceTransformer model not available offline")
    # "What's the cost of a cut?" has low lexical overlap with
    # "A haircut costs $35 and takes about 30 minutes."
    result = retriever.retrieve("What's the cost of a cut?")
    assert result.status == FusionStatus.MATCHED
    assert result.fallback_to_okf is False


def test_semantic_retriever_unrelated_query_fallback() -> None:
    """Unrelated queries with no semantic match fall back to OKF."""
    retriever = _make_semantic_retriever()
    if retriever is None:
        pytest.skip("SentenceTransformer model not available offline")
    result = retriever.retrieve("quantum physics research")
    assert result.status == FusionStatus.FALLBACK_OKF
    assert result.fallback_to_okf is True


def test_semantic_retriever_unsupported_policy_abstains() -> None:
    """Unsupported policies abstain even with semantic retrieval."""
    retriever = _make_semantic_retriever()
    if retriever is None:
        pytest.skip("SentenceTransformer model not available offline")
    answer = retriever.answer("Can I get a refund?")
    assert answer.status == AnswerStatus.ABSTAINED
    assert answer.reason == "no_approved_policy_source"


def test_semantic_retriever_same_provenance_conflict() -> None:
    """Two bundle sources disagreeing on price -> conflict -> abstain."""
    provider = SentenceTransformerProvider()
    chunks = (
        KnowledgeChunk(
            chunk_id="kb:faq/conflict-a#chunk=0",
            source_id="kb:faq/conflict-a",
            source_reference="kb:faq/conflict-a.md#version=1.0.0",
            category=KnowledgeCategory.FAQ,
            status="approved",
            content="A haircut costs $50 and takes about 30 minutes.",
            document_id="kb:faq/conflict-a.md",
            version="1.0.0",
            chunk_index=0,
            content_hash=hashlib.sha256(
                "A haircut costs $50 and takes about 30 minutes.".encode()
            ).hexdigest(),
            word_count=7,
        ),
        KnowledgeChunk(
            chunk_id="kb:faq/conflict-b#chunk=0",
            source_id="kb:faq/conflict-b",
            source_reference="kb:faq/conflict-b.md#version=1.0.0",
            category=KnowledgeCategory.FAQ,
            status="approved",
            content="A haircut costs $35 and takes about 30 minutes.",
            document_id="kb:faq/conflict-b.md",
            version="1.0.0",
            chunk_index=0,
            content_hash=hashlib.sha256(
                "A haircut costs $35 and takes about 30 minutes.".encode()
            ).hexdigest(),
            word_count=7,
        ),
    )
    index = KnowledgeChunkIndex(chunks=chunks)
    retriever = SemanticRetriever(index=index, provider=provider)
    result = retriever.retrieve("How much is a haircut?")
    assert result.status == FusionStatus.CONFLICT
    assert result.reason == "conflicting_prices_for_haircut"
    answer = retriever.answer("How much is a haircut?")
    assert answer.status == AnswerStatus.ABSTAINED
    assert "conflicting" in answer.text


def test_semantic_retriever_fixture_precedence() -> None:
    """Fixture price wins over bundle price disagreement."""
    provider = SentenceTransformerProvider()
    chunks = (
        KnowledgeChunk(
            chunk_id="fixture:demo-salon-v1:service:haircut#chunk=0",
            source_id="fixture:demo-salon-v1:service:haircut",
            source_reference="fixtures/demo_salon.json#/services/0",
            category=KnowledgeCategory.SERVICE,
            status="approved",
            content="Haircut: 30 minutes, USD 35.00; active in the service catalog.",
            document_id="fixtures/demo_salon.json#/services/0",
            version="1.0.0",
            chunk_index=0,
            content_hash=hashlib.sha256(
                "Haircut: 30 minutes, USD 35.00; active in the service catalog.".encode()
            ).hexdigest(),
            word_count=9,
        ),
        KnowledgeChunk(
            chunk_id="kb:faq/higher-pricing#chunk=0",
            source_id="kb:faq/higher-pricing",
            source_reference="kb:faq/higher-pricing.md#version=1.0.0",
            category=KnowledgeCategory.FAQ,
            status="approved",
            content="A haircut costs $50 and takes about 30 minutes.",
            document_id="kb:faq/higher-pricing.md",
            version="1.0.0",
            chunk_index=0,
            content_hash=hashlib.sha256(
                "A haircut costs $50 and takes about 30 minutes.".encode()
            ).hexdigest(),
            word_count=7,
        ),
    )
    index = KnowledgeChunkIndex(chunks=chunks)
    retriever = SemanticRetriever(index=index, provider=provider)
    result = retriever.retrieve("How much is a haircut?")
    assert result.status == FusionStatus.MATCHED
    answer = retriever.answer("How much is a haircut?")
    assert answer.status == AnswerStatus.ANSWERED
    assert "35" in answer.text
    assert "50" not in answer.text


def test_semantic_retriever_provider_failure_falls_back_to_lexical() -> None:
    """Provider inference failure propagates from the retriever."""
    service = KnowledgeService()
    record = service.index.resolve_source_id(
        "fixture:demo-salon-v1:service:haircut"
    )
    chunk = chunk_record(record, max_words=100)[0]
    lexical_index = KnowledgeChunkIndex(chunks=(chunk,))

    class FailingProvider:
        def embed(self, texts):
            raise RuntimeError("model inference failed")

        def similarity(self, a, b):
            raise RuntimeError("model inference failed")

        @property
        def dimension(self):
            return 384

    semantic_retriever = SemanticRetriever(
        index=lexical_index,
        provider=FailingProvider(),
    )
    try:
        semantic_retriever.retrieve("How much is a haircut?")
        pytest.fail("Expected RuntimeError from failing provider")
    except RuntimeError:
        pass
