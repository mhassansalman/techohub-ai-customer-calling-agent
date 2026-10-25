# 07 — Knowledge Architecture: OKF-First, Vector Retrieval Later

## Decision and terminology

- **Initial knowledge representation:** **Open Knowledge Format (OKF)**: Git-friendly Markdown bundle with structured YAML frontmatter and an entry point `index.md` (see https://okf.md/).
- **Initial retrieval implementation:** `OKFKnowledgeAdapter`, which reads a structured index, resolves relevant documents, checks metadata/policy/version, and returns evidence.
- **Extension contract:** `KnowledgeProvider` supports alternative vector/hybrid retrievers later.
- **ChromaDB / FAISS / Milvus:** **architecture only**, explicitly excluded from initial implementation; no dependencies/service startup required.

### Important technical nuance

OKF is a **knowledge format**, not a drop-in vector-database product. Loading its documents to ground generated answers is *retrieval-augmented generation in the general sense*, even without embeddings. The explicit architectural choice is **OKF navigation without vector indexing** at first—not 'no retrieval'.

## Example structure (illustrative, not a real business policy)

```text
knowledge_bundle/
  index.md
  faq/
    business_hours.md
    services.md
  policies/
    cancellation.md
    refund.md
  procedures/
    escalation.md
  glossary/
    terms.md
```

Example content format:

```markdown
---
type: reference
title: Business hours
source_id: kb:faq/business_hours
version: 1.0.0
status: approved
---
# Business hours
[PLACEHOLDER: insert approved business hours before demo]
```

The sample metadata fields other than OKF-required fields are **application conventions**; validate them separately.

## Approved evidence contract

```json
{
  "document_id": "kb:policies/cancellation",
  "title": "Cancellation policy",
  "source_uri": "knowledge_bundle/policies/cancellation.md",
  "version": "1.0.0",
  "excerpt": "[approved excerpt]",
  "effective_at": null,
  "retrieval_method": "okf_index",
  "score": null
}
```

Do not fabricate `score` for exact rule/index matching. Cite only approved active sources; disallow archived/draft or mismatched-tenant policies.

## Retrieval flow

1. Ingest/validate OKF bundle, check index and frontmatter validity.
2. On query, detect relevant topics/metadata -> follow index and topic links -> retrieve exact approved documents.
3. Return evidence excerpts with stable document IDs/version.
4. Agent or workflow combines evidence with **live** business data if needed.
5. Final response grounds policy claims in evidence; ambiguous/missing -> abstain, ask or escalate.

**Different source of truth:** schedule status must come from `BookingProvider`; customer-specific records from `CRMProvider`; unresolved issue progress from `TicketProvider`. Never retrieve them from static OKF policy files.

## Why abstraction matters

```python
class KnowledgeProvider(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[Evidence]: ...
    async def get_document(self, document_id: str) -> KnowledgeDocument: ...
```

Candidate future adapters: `ChromaKnowledgeAdapter`, `FaissKnowledgeAdapter`, `MilvusKnowledgeAdapter`, `HybridKnowledgeAdapter`. Each maps provider-specific results to identical `Evidence` objects.

## When to consider vector search

- Search fails to find relevant documents for paraphrased/vague real customer queries.
- Bundle becomes broad, poorly navigable or too expensive to scan heuristically.
- Evaluation shows vector/hybrid significantly improves retrieval recall **without** reducing policy precision.

Before adding it: gather representative queries, measure retrieval recall@k and answer grounding, and verify data governance. ChromaDB is the preferred *future* small-scale vector adapter, not the selected initial repository.

## Knowledge evaluation

- Exact policy query retrieves exact version.
- Paraphrased questions land on correct source.
- Conflicting policy versions respect effective dates/status and tenant boundary.
- Unsupported question returns 'not available' safely.
- Injection in Markdown is treated as untrusted content, not system instructions.
- Model must never invent an approval, price or policy not present in trusted evidence.
