from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from backend.fixtures import load_demo_salon_fixture
from backend.knowledge import (
    DEFAULT_KNOWLEDGE_BUNDLE,
    KnowledgeCategory,
    KnowledgeRecord,
    _approved_markdown_records,
    _fixture_records,
    _parse_frontmatter,
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class KnowledgeChunk:
    """A deterministic, approved-only chunk of a knowledge document."""

    chunk_id: str
    source_id: str
    source_reference: str
    category: KnowledgeCategory
    status: str
    content: str
    document_id: str
    version: str
    chunk_index: int
    content_hash: str
    word_count: int


@dataclass(frozen=True)
class KnowledgeChunkIndex:
    """An in-memory, repeatable index of approved knowledge chunks."""

    chunks: tuple[KnowledgeChunk, ...]

    def __post_init__(self) -> None:
        chunks = tuple(self.chunks)
        if not chunks:
            raise ValueError("knowledge chunk index must contain at least one chunk")
        ids = {chunk.chunk_id for chunk in chunks}
        if len(ids) != len(chunks):
            raise ValueError("knowledge chunk IDs must be unique")
        object.__setattr__(self, "chunks", chunks)

    def chunk_by_id(self, chunk_id: str) -> KnowledgeChunk:
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                return chunk
        raise KeyError(f"chunk not found: {chunk_id}")

    def chunks_by_source(self, source_id: str) -> tuple[KnowledgeChunk, ...]:
        return tuple(
            chunk for chunk in self.chunks if chunk.source_id == source_id
        )

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(chunk.source_id for chunk in self.chunks))


def _extract_document_id_and_version(source_reference: str) -> tuple[str, str]:
    """Split an OKF source_reference into (document_id, version).

    source_reference has the form ``relative/path.md#version=1.0.0``.
    """
    document_id = source_reference
    version = "1.0.0"
    if "#version=" in source_reference:
        document_id, version_part = source_reference.rsplit("#version=", 1)
        version = version_part.strip()
    return document_id, version


def _split_into_chunks(content: str, max_words: int) -> list[str]:
    """Deterministically split content into chunks of at most max_words words.

    Paragraphs are kept intact when possible; long paragraphs are split at
    sentence boundaries. Whitespace is normalized but word order is preserved.
    """
    if max_words <= 0:
        raise ValueError("max_words must be positive")

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks: list[str] = []

    for paragraph in paragraphs:
        words = _WORD.findall(paragraph)
        if len(words) <= max_words:
            chunks.append(paragraph)
            continue

        sentences = [s.strip() for s in _SENTENCE.split(paragraph) if s.strip()]
        current: list[str] = []
        current_words = 0

        for sentence in sentences:
            sentence_words = _WORD.findall(sentence)
            if current_words + len(sentence_words) > max_words and current:
                chunks.append(" ".join(current))
                current = []
                current_words = 0
            if len(sentence_words) > max_words:
                for start in range(0, len(sentence_words), max_words):
                    window = sentence_words[start:start + max_words]
                    chunks.append(" ".join(window))
                continue
            current.extend(sentence_words)
            current_words += len(sentence_words)

        if current:
            chunks.append(" ".join(current))

    return chunks


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_record(
    record: KnowledgeRecord,
    max_words: int = 120,
) -> tuple[KnowledgeChunk, ...]:
    """Chunk a single approved KnowledgeRecord into stable KnowledgeChunks.

    Chunk IDs are deterministic: ``{source_id}#chunk={index}``. Each chunk
    carries a SHA-256 content hash so tampering is detectable.
    """
    document_id, version = _extract_document_id_and_version(record.source_reference)
    pieces = _split_into_chunks(record.content, max_words)
    result: list[KnowledgeChunk] = []
    for index, chunk_text in enumerate(pieces):
        result.append(
            KnowledgeChunk(
                chunk_id=f"{record.source_id}#chunk={index}",
                source_id=record.source_id,
                source_reference=record.source_reference,
                category=record.category,
                status=record.status,
                content=chunk_text,
                document_id=document_id,
                version=version,
                chunk_index=index,
                content_hash=_sha256(chunk_text),
                word_count=len(_WORD.findall(chunk_text)),
            )
        )
    return tuple(result)


def load_approved_chunks(
    bundle_path: Path | None = None,
    max_words: int = 120,
    include_fixture: bool = True,
) -> KnowledgeChunkIndex:
    """Load approved chunks from the OKF knowledge bundle.

    Reuses the existing OKF validation and path-security logic in
    ``backend.knowledge._approved_markdown_records``. Only ``status: approved``
    records are admitted; unsafe or unapproved paths raise before any chunk is
    produced. Optionally includes fixture-derived approved records so the
    canonical fixture remains the authoritative source for prices, hours and
    durations.
    """
    if max_words <= 0:
        raise ValueError("max_words must be positive")

    resolved_bundle = (bundle_path or DEFAULT_KNOWLEDGE_BUNDLE).resolve(strict=True)
    records: list[KnowledgeRecord] = list(_approved_markdown_records(resolved_bundle))

    if include_fixture:
        fixture = load_demo_salon_fixture()
        records.extend(_fixture_records(fixture))

    chunks: list[KnowledgeChunk] = []
    for record in records:
        chunks.extend(chunk_record(record, max_words=max_words))

    return KnowledgeChunkIndex(chunks=tuple(chunks))
