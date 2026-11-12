from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.chunker import KnowledgeChunk, KnowledgeChunkIndex, chunk_record, load_approved_chunks
from backend.fixtures import load_demo_salon_fixture
from backend.knowledge import KnowledgeCategory, KnowledgeService, build_knowledge_index


def _write_faq(bundle: Path, relative: str, frontmatter: str, content: str) -> Path:
    path = bundle / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\n{frontmatter}---\n{content}", encoding="utf-8"
    )
    return path


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_chunk_record_produces_stable_ids_and_hashes() -> None:
    service = KnowledgeService()
    record = service.index.resolve_source_id(
        "fixture:demo-salon-v1:service:haircut"
    )
    chunks = chunk_record(record, max_words=50)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_id == "fixture:demo-salon-v1:service:haircut#chunk=0"
    assert chunk.source_id == "fixture:demo-salon-v1:service:haircut"
    assert chunk.status == "approved"
    assert chunk.content_hash == _sha256(chunk.content)
    assert chunk.word_count == len(chunk.content.split())
    assert "haircut" in chunk.content.casefold()
    assert "35.00" in chunk.content


def test_chunk_record_is_deterministic() -> None:
    service = KnowledgeService()
    record = service.index.resolve_source_id(
        "fixture:demo-salon-v1:hours:monday"
    )
    first = chunk_record(record, max_words=30)
    second = chunk_record(record, max_words=30)

    assert first == second
    assert [c.content_hash for c in first] == [c.content_hash for c in second]


def test_chunk_respects_max_word_boundary() -> None:
    service = KnowledgeService()
    record = service.index.resolve_source_id(
        "fixture:demo-salon-v1:hours:monday"
    )
    chunks = chunk_record(record, max_words=10)

    for chunk in chunks:
        assert len(chunk.content.split()) <= 10, chunk.content
    assert " ".join(c.content for c in chunks).strip() == record.content.strip()


def test_chunk_ids_are_unique_and_stable() -> None:
    service = KnowledgeService()
    record = service.index.resolve_source_id(
        "fixture:demo-salon-v1:service:beard-trim"
    )
    chunks = chunk_record(record, max_words=100)

    ids = [chunk.chunk_id for chunk in chunks]
    assert len(ids) == len(set(ids))
    assert all(
        chunk_id.startswith("fixture:demo-salon-v1:service:beard-trim#chunk=")
        for chunk_id in ids
    )


def test_load_approved_chunks_loads_real_bundle() -> None:
    index = load_approved_chunks(max_words=100)

    assert isinstance(index, KnowledgeChunkIndex)
    assert len(index.chunks) > 0
    for chunk in index.chunks:
        assert chunk.status == "approved"
        assert chunk.content_hash == _sha256(chunk.content)
        assert chunk.chunk_index >= 0
        assert chunk.word_count > 0
        assert chunk.word_count <= 100


def test_load_approved_chunks_contains_fixture_supported_facts() -> None:
    index = load_approved_chunks(max_words=100)

    source_ids = set(index.source_ids)
    assert any("demo-salon-v1:service:haircut" in sid for sid in source_ids)
    assert any("demo-salon-v1:service:beard-trim" in sid for sid in source_ids)
    assert any("demo-salon-v1:service:haircut-beard" in sid for sid in source_ids)
    assert any("demo-salon-v1:hours:monday" in sid for sid in source_ids)


def test_load_approved_chunks_is_deterministic() -> None:
    first = load_approved_chunks(max_words=80)
    second = load_approved_chunks(max_words=80)

    assert first.chunks == second.chunks
    assert first.source_ids == second.source_ids
    assert [c.content_hash for c in first.chunks] == [
        c.content_hash for c in second.chunks
    ]


def test_chunk_by_id_and_chunks_by_source() -> None:
    index = load_approved_chunks(max_words=100)

    haircut_chunks = index.chunks_by_source("fixture:demo-salon-v1:service:haircut")
    assert len(haircut_chunks) >= 1
    assert all(
        chunk.source_id == "fixture:demo-salon-v1:service:haircut"
        for chunk in haircut_chunks
    )

    chunk = index.chunk_by_id(haircut_chunks[0].chunk_id)
    assert chunk.chunk_id == haircut_chunks[0].chunk_id
    with pytest.raises(KeyError):
        index.chunk_by_id("does-not-exist#chunk=0")


def _bundle_with_index(bundle: Path, index_content: str) -> None:
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "index.md").write_text(index_content, encoding="utf-8")


def test_load_approved_chunks_rejects_unapproved_record(tmp_path: Path) -> None:
    bundle = tmp_path / "knowledge_bundle"
    _bundle_with_index(bundle, "[Draft](faq/draft.md)\n")
    _write_faq(
        bundle,
        "faq/draft.md",
        "type: faq\ntitle: Draft policy\nsource_id: kb:faq:draft\nversion: 0.1.0\nstatus: draft\n",
        "Draft content.\n",
    )

    with pytest.raises(ValueError, match="not approved"):
        load_approved_chunks(bundle_path=bundle, include_fixture=False)


def test_load_approved_chunks_rejects_unsafe_path(tmp_path: Path) -> None:
    bundle = tmp_path / "knowledge_bundle"
    _bundle_with_index(bundle, "[Escape](../outside.md)\n")
    (tmp_path / "outside.md").write_text("outside\n", encoding="utf-8")

    with pytest.raises(ValueError, match="escapes its bundle"):
        load_approved_chunks(bundle_path=bundle, include_fixture=False)


def test_load_approved_chunks_rejects_missing_frontmatter(tmp_path: Path) -> None:
    bundle = tmp_path / "knowledge_bundle"
    _bundle_with_index(bundle, "[No frontmatter](faq/nofm.md)\n")
    (bundle / "faq").mkdir(parents=True, exist_ok=True)
    (bundle / "faq" / "nofm.md").write_text("Just content, no frontmatter.\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no YAML frontmatter"):
        load_approved_chunks(bundle_path=bundle, include_fixture=False)


def test_load_approved_chunks_rejects_incomplete_metadata(tmp_path: Path) -> None:
    bundle = tmp_path / "knowledge_bundle"
    _bundle_with_index(bundle, "[Incomplete](faq/inc.md)\n")
    _write_faq(
        bundle,
        "faq/inc.md",
        "type: faq\ntitle: Incomplete\nstatus: approved\n",
        "Missing source_id and version.\n",
    )

    with pytest.raises(ValueError, match="incomplete"):
        load_approved_chunks(bundle_path=bundle, include_fixture=False)


def test_load_approved_chunks_rejects_empty_content(tmp_path: Path) -> None:
    bundle = tmp_path / "knowledge_bundle"
    _bundle_with_index(bundle, "[Empty](faq/empty.md)\n")
    _write_faq(
        bundle,
        "faq/empty.md",
        "type: faq\ntitle: Empty\nsource_id: kb:faq:empty\nversion: 1.0.0\nstatus: approved\nkeywords:\n  - empty\n",
        "",
    )

    with pytest.raises(ValueError, match="content is empty"):
        load_approved_chunks(bundle_path=bundle, include_fixture=False)


def test_load_approved_chunks_rejects_missing_bundle() -> None:
    with pytest.raises(FileNotFoundError):
        load_approved_chunks(bundle_path=Path("nonexistent-bundle"), include_fixture=False)


def test_chunk_index_rejects_duplicate_ids() -> None:
    chunk = KnowledgeChunk(
        chunk_id="x#chunk=0",
        source_id="x",
        source_reference="x.md#version=1.0.0",
        category=KnowledgeCategory.FAQ,
        status="approved",
        content="text",
        document_id="x.md",
        version="1.0.0",
        chunk_index=0,
        content_hash=_sha256("text"),
        word_count=1,
    )
    with pytest.raises(ValueError, match="unique"):
        KnowledgeChunkIndex(chunks=(chunk, chunk))


def test_fixture_records_remain_authoritative() -> None:
    fixture = load_demo_salon_fixture()
    services = {s.service_id: s for s in fixture.services}
    assert services["haircut"].price_amount == 35
    assert services["haircut"].duration_minutes == 30
    assert services["beard-trim"].price_amount == 18
    assert services["beard-trim"].duration_minutes == 20
    assert services["haircut-beard"].price_amount == 45
    assert services["haircut-beard"].duration_minutes == 45

    index = load_approved_chunks(max_words=100)
    haircut = index.chunks_by_source("fixture:demo-salon-v1:service:haircut")[0]
    assert "35.00" in haircut.content
    assert "30 minutes" in haircut.content
