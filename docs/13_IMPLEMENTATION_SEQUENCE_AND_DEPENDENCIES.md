# 13 — Implementation Dependency Order (Not the Weekly Timeline)

> The user wants a **separate new chat** to design the month-by-month/weekly schedule. This document supplies logical engineering dependencies only; it does **not** allocate weeks or pretend the implementation has started.

## Dependencies and recommended sequence

1. **Business domain and approved intents:** choose demo business, author truthful approved FAQ and sample dialogues. Without this, router labels, schema and acceptance tests are hypothetical.
2. **Contracts and local proof:** define `CustomerMessage`, `AgentResponse`, `RoutingDecision`, `Evidence`, canonical customer/booking/ticket models, permission/context and error enums; build local provider stubs.
3. **Minimal backend + state + text:** FastAPI routes, SQLite migrations, session records, a simple multi-turn LangGraph, baseline rule router and text web UI.
4. **OKF & grounding:** validate bundle, index search/retrieval, return source IDs, test unsupported queries and prompt injection.
5. **Local CRM/booking/tickets:** seed safe demo data, add CRUD domain services, constraints, verification, confirmations, ticket queue; enable a meaningful complete customer scenario.
6. **MCP tool exposure:** only after domain-service interfaces work; demonstrate one or more tools through MCP and compare with native direct calls.
7. **Browser voice:** implement channel audio capture, STT-before-core, TTS-after-core, sessions, text fallback, ASR error handling and basic latency benchmarks.
8. **Routing/agent enhancement:** add complexity classification, candidate Jev adapter if accessible, one specialist agent if justified, evaluation and safe escalation.
9. **Optional external integrations:** prioritize a single provider sandbox contract test (e.g. Google Calendar) rather than attempting every CRM/booking/ticket backend.
10. **Telephony experiment:** Twilio or SIP mock/real sandbox with budget, webhooks and call events; SIM gateway strictly experimental.
11. **Final quality:** error/fallback matrix, end-to-end tests, README, screenshots, architecture, database schema, known limitations and demo video.

## Critical path for marks

A functioning browser voice + text fallback -> three supported intents -> approved KB -> persisted transcript/intent/outcome -> escalation and safe policy disclosure -> tested demonstration. Everything else is added only when it does not jeopardize this path.

## Engineering go/no-go gates

| Gate | Evidence | If not passed |
|---|---|---|
| Business scope approved | Intent taxonomy + vetted policies | Do not train/demo invented policies |
| Core text path passes | E2E supported FAQ and handoff | Don't add telephony yet |
| Mutation safety passes | No duplicate/unconfirmed bookings | Disable booking writes |
| Voice demo passes | STT -> graph -> TTS + fallback | Reduce model complexity or switch provider |
| Optional router proven | Jev accessible + benchmark >= baseline | Use rule/LLM fallback |
| External integration proven | Auth + contract test + rollback | Label as architecture-only |
| Demo ready | All assignment checklist artifacts | No optional feature displacement |

## Suggested Agile translation for the new chat

Convert each dependency into: **Epic -> User stories -> implementation tasks -> acceptance criteria -> test proof -> weekly deliverable**. Allocate realistic contingency for hardware issues, tests, provider setup and final demo. Do not silently turn a four-week target into mandatory full production telephony.
