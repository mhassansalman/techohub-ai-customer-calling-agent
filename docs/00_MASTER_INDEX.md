# Documentation Master Index & Status Ledger

> **Project:** AI Customer Calling Agent — modular, knowledge-grounded, hybrid agentic customer-service assistant.  
> **Project phase:** requirements and architecture are being finalized; implementation and actual API integrations are **not yet evidenced**.  
> **Planning horizon for next chat:** one month: three weeks for a functional working prototype, fourth week for telephony experiments, hardening, testing and submission.

## Index

| File | Use |
|---|---|
| `01_PROJECT_CHARTER_AND_SCOPE.md` | Problem, goals, users, assumptions, in/out of scope |
| `02_SRS_FUNCTIONAL_NONFUNCTIONAL.md` | Testable requirements, flows, acceptance criteria |
| `03_SYSTEM_ARCHITECTURE.md` | C4-inspired system/containers + hexagonal ports and adapters |
| `04_LANGGRAPH_ROUTING_AND_AGENTS.md` | Intent/complexity routing, Jev clarification, workflows and agents |
| `05_BUSINESS_CAPABILITIES_CRM_BOOKING_TICKETS_MCP.md` | Why each capability exists; MCP/direct interfaces |
| `06_CHANNELS_SPEECH_AND_TELEPHONY.md` | Text/voice/telephony flow, voice conversion placement, provider options |
| `07_KNOWLEDGE_OKF_RETRIEVAL_AND_RAG.md` | OKF-first navigation and vector adapter future support |
| `08_DATA_MODELS_AND_DATABASE.md` | Logical entities, relations, provider-neutral contracts |
| `09_SECURITY_PRIVACY_AND_RELIABILITY.md` | Verification, consent, confirmation, policy, logs and recovery |
| `10_TECH_STACK_DEPLOYMENT_AND_CONFIG.md` | Chosen/proposed tech, non-Docker setup, configuration |
| `11_TESTING_EVALUATION_AND_DEMOS.md` | Tests for core, speech, RAG, routing, integrations, demos |
| `12_ARCHITECTURE_DECISIONS_AND_OPEN_QUESTIONS.md` | Decisions, assumptions, risks and unresolved items |
| `13_IMPLEMENTATION_SEQUENCE_AND_DEPENDENCIES.md` | Dependency order (not weekly allocation) |
| `14_RUBRIC_TRACEABILITY_AND_DELIVERABLES.md` | Assignment mapping, 100-point rubric, evidence required |
| `15_GLOSSARY_AND_REFERENCES.md` | Terminology and authoritative sources |
| `16_CONVERSATION_SCENARIOS.md` | Representative supported/unsupported customer flows |

## Decision status: read carefully

### Finalized architectural principles

- Provider-independent, ports-and-adapters design.
- Unified **text request** passed to LangGraph. Source channel/session information travels with it.
- Simple requests -> controlled workflows/tools; complex -> specialized reasoning agent(s); sensitive/uncertain -> escalation or verification.
- Separate interfaces for CRM, booking, tickets, knowledge, voice providers and channels.
- OKF as the initial knowledge source; vector retrieval *extension points*, not an existing delivery.
- Text/browser-voice required in implementation plan; telephony an optional upgrade/experiment.
- Audit logging, automated-assistant disclosure, privacy/consent and no unauthorized commitments.

### Preferred initial implementations / subject to confirmation

- Python + FastAPI; React/Vite frontend; SQLite/SQLAlchemy; LangGraph; locally runnable environment.
- OKF Markdown knowledge bundle with index navigation and grounded source references.
- A `RuleBasedRouter` baseline and optionally TypeSafe Jev integration behind `IntentRouter` when technically, financially, and legally feasible.
- Local booking/CRM/ticket adapters; MCP exposure when integration reuse justifies it.
- Speech-to-text e.g. faster-whisper and speech synthesis e.g. Piper/browser TTS; must benchmark the user's machine.

### Future or explicitly excluded from first cut

- Production telephony (Twilio/SIP) and personal SIM gateway until validated.
- Paid cloud STT/TTS/LLM providers.
- Vector adapters: ChromaDB, FAISS, Milvus, hybrid search (architecturally allowed, not implemented).
- Third-party CRM/helpdesk/scheduling implementations unless one is deliberately selected as the external-integration demonstration.
- Enterprise microservices, scale-out Milvus, real customer data or production-grade telecom compliance.

### Open for the next chat / before final SRS approval

1. Choose target business domain (clinic, salon, repair center, retail, etc.). No domain has yet been formally selected.
2. Define supported core intents and business-specific policies; no real company policy should be invented.
3. Confirm hardware constraints and local inference benchmark.
4. Check Jev access, pricing, integration SDK, fallback behavior and routing test data.
5. Select external integration proof of concept, if any (e.g. Google Calendar rather than three external services).
6. Confirm project dates, available daily hours, team size and university review cadence.
7. Confirm which optional features are worth building versus demonstrating as architecture-only.

## Single-line architecture

`Text/Voice/Telephony -> Channel Adapter -> optional STT -> Unified Text Request -> LangGraph (Jev/rules/LLM router) -> Simple Workflow | Specialist Agent | Escalation -> Native Services / MCP exposed capabilities -> Provider Ports -> Local | External Adapters -> Validated Text Answer -> optional TTS -> Original Channel; with state, security, audits throughout.`
