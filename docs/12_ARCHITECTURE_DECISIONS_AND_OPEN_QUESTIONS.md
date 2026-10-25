# 12 — Architecture Decision Records (ADRs), Risks and Open Questions

> Status values: **accepted principle**, **preferred**, **conditional**, **excluded now**, **unresolved**. Never confuse conceptual support with delivered code.

| ADR | Decision | Status | Rationale / qualification |
|---|---|---|---|
| ADR-001 | Modular monolith + ports/adapters | Accepted principle | Swap local/external providers; keep business logic stable |
| ADR-002 | Core operates on normalized text turns | Accepted principle | Consistent routing across typed, browser voice, telephony |
| ADR-003 | Channel transport before STT; STT before LangGraph | Accepted principle | Channel handles sessions/events; core stays audio-independent |
| ADR-004 | Hybrid LangGraph: simple tools/workflows, complex specialist, guarded human | Accepted principle | Lower latency and safer routing vs mandatory multi-agent everything |
| ADR-005 | Native tools for internal operations | Accepted principle | Direct, low-latency, easily tested |
| ADR-006 | MCP expose reusable CRM/booking/ticket operations | Preferred | MCP valuable at service boundaries, not mandatory for every call |
| ADR-007 | Separate CRM / booking / ticket ports | Accepted principle | Distinct domain responsibilities; can share local DB |
| ADR-008 | Local business providers first | Preferred | No paid API required; external provider replacement possible |
| ADR-009 | OKF knowledge-first | Accepted principle | Small approved KB, structured Markdown, versionable navigation |
| ADR-010 | ChromaDB, FAISS, Milvus extension interface only | Excluded now | Avoid premature vector complexity; not implemented/tested |
| ADR-011 | TypeSafe Jev for intent/complexity/risk candidate | Conditional | Real decision model, not JSON format; availability/cost/performance TBD |
| ADR-012 | `IntentRouter` fallback rules / structured LLM | Accepted principle | Work even if Jev unavailable; safe low-confidence path |
| ADR-013 | Text + browser voice baseline | Accepted principle | Meets assignment; telephone not required |
| ADR-014 | Twilio/SIP optional, personal SIM experimental | Excluded now | Telecom APIs/hardware/fees and call-audio restrictions |
| ADR-015 | Pluggable STT/TTS/LLM providers | Accepted principle | Local first, cloud later |
| ADR-016 | Identity, consent, explicit confirmations, idempotency | Accepted principle | Prevent leakage, unsafe promises and duplicate actions |
| ADR-017 | SQLite/SQLAlchemy, FastAPI, React/Vite, Ollama | Preferred | Confirm hardware and actual code before calling finalized |
| ADR-018 | No Docker for initial demo | Preferred constraint | User's local-machine limitation and speed of setup |
| ADR-019 | One-month delivery outline: 3 core weeks + optional week 4 | Planning constraint | Exact weekly backlog intentionally deferred to next chat |

## Biggest project risks

1. **Wrong business scenario** -> unclear intent acceptance and invalid knowledge data. Resolve first.
2. **Too many enhancements** -> core graded voice/FAQ/hand-off not demo-ready. Preserve MVP critical path.
3. **Local model too slow** -> browser voice unusable. Benchmark before architecture crystallizes provider list.
4. **Jev API access/cost** -> router blocked. Make rules fallback first.
5. **MCP overengineering** -> extra services without user value. Prove one MCP flow, expand as justified.
6. **Calendar integration mismatch** -> custom booking rules differ from Google Calendar. Contract tests.
7. **SIM telephony impossible** -> don't anchor week-4 success on it.
8. **Policy hallucination/unsafe mutation** -> citations, deterministic authorization and confirmation.
9. **Imprecise claim of future support** -> label 'adapter-ready only' explicitly.
10. **Documentation drift** -> update status ledger and ADRs at each weekly review.

## Decisions requiring user input for next planning chat

- **Which business?** Salon/spa, clinic, repair shop, retail or another?
- **Team:** individual or team? Hours/day and exact due/review dates?
- **Language:** English mandatory; Urdu optional or mandatory?
- **Machine:** CPU/RAM/GPU and what can run locally?
- **Integration stretch:** real calendar, Jev, telephony: priority ranking and budget?
- **Human escalation:** local ticket queue vs staff-in-the-loop live transfer demonstration?

## Explicit statement for SRS

'Interfaces allow optional integration with external CRM/scheduling/helpdesk, telephony, speech providers and vector retrieval technology. Unless marked delivered and tested, these are architectural extension points only. The initial prototype uses approved OKF knowledge and local business adapters with browser voice and text.'
