# AI Customer Calling Agent
## One-Month Agile Development Plan | 19 October–15 November 2026

**Project:** Voice-capable AI Customer Calling Agent for a fictional Demo Salon  
**Submitted plan date:** Sunday, 18 October 2026 | **Owner:** Individual student developer  
**Budget / platform:** $0 billed spend; Windows 10, ~8 GB RAM; no Docker or local LLM  
**Planning status:** Architecture and synthetic dataset prepared; implementation and external voice/LLM integrations **not yet verified**.

## 1. Problem, goals and scope

Small customer-service teams repeatedly answer hours/policy questions and process appointment availability or support requests. A safe automated service must avoid invented business commitments, support limited follow-up dialogue and make unresolved issues visible to a human operator.

**Goal:** Deliver a modular browser text/voice and simulated-audio-call agent with working English STT/TTS, a **real hosted LLM intent classifier**, a rules-based fast path and fallback, approved OKF-grounded answers, synthetic read-only salon slot lookup, a persisted customer-confirmed support ticket and protected staff access. Demonstrate the three independent intents `faq_business_hours`, `appointment_availability`, and `human_request` with logs, tests and source attribution.

**Scope tiers (P0/P1/P2 are the only priority tiers):**

| P0 — mandatory and assessed | P1 — optional for assessment, planned for full implementation if no delays | P2 — not implemented |
|---|---|---|
| Text, browser microphone audio and simulated-call audio; four-adapter common interface; voice STT/TTS; bounded dialogue | Urdu speech/English translation/Urdu TTS, multilingual extension ports | Real PSTN/SIP/Twilio/SIM telephony; retain adapter interface |
| Rules fast path + validated **hosted LLM classification** + LangGraph + local tool-first execution | Complex-task FAQ/booking/support agents, grounded natural language enhancement | Hosted Jev/jevos; Ollama/local LLM; billed AI models |
| Three local capability tools; SQLite sessions/availability/tickets, staff protected read, audit/consent | Booking create/reschedule/cancel with authorization, confirmation and idempotency; local CRM and advanced ticketing | External CRM/helpdesk/booking providers |
| OKF knowledge provider with deterministic retrieval, English response and browser TTS | Semantic/vector RAG alongside OKF with evidence fusion; local MCP tools/server/client; analytics/UI | External MCP integrations, Docker, paid cloud |

The architecture retains interfaces for P1/P2 without treating absent implementations as working. The direct appointment tool remains P0 even if BookingAgent is absent; direct ticket queueing remains P0 even if SupportAgent/MCP is absent. When both OKF and RAG work, deduplicate and reconcile approved evidence into one grounded answer; when RAG has no results, use OKF; when neither has evidence, clarify or offer a customer-confirmed ticket.

## 2. Implementation strategy and dependency order

Use **four one-week Agile/Scrum-inspired sprints** (solo implementation, daily task tracking, Sunday review). Start with a working vertical slice and add optional providers through stable ports: `ChannelAdapter`, `IntentClassifier`, `KnowledgeProvider`, `ToolProvider`, `AgentProvider`, `TranslationProvider`, `BookingProvider`, `TicketProvider`. Speech transcription occurs before normalized channel ingestion; for P1 Urdu, recognize Urdu → translate to English → core processing → translate response to Urdu → synthesize Urdu audio. English processing remains P0; translation does not alter business authority.

**Operational prerequisites:** In Week 1 verify an eligible **free hosted LLM account/model** (Groq preferred), quotas/privacy and test at least one real classification; test browser microphone/STT/TTS in the actual demonstration browser. Fast path may bypass the LLM for obvious utterances, but an LLM adapter **must work and be demonstrated** for P0. If provider/browsers fail, keep users safe through rules/clarification/typed fallback and log the unmet P0 gate; do not claim fallback alone fulfills LLM or audible-voice assessment.

Protect sensitive operations server-side. P0 availability reads never book. P0 ticket creation requires user confirmation and returns the actual stored queued ID/status, with credential-protected staff GET. P1 booking changes require identity/authorization, fresh slot check, exact readback, affirmative confirmation, atomic idempotent transaction and audit. Only fictional salon data are used.

## 3. Four-week sprint plan with measurable checkpoints

### Week 1 | 19–25 October — P0 foundation (7 days)
**Goal:** Windows-native repo, SQLite fixture integration, channel/session contracts and a working typed vertical slice; early real speech and hosted-LLM feasibility.

**Key work:** environment and data validator; FastAPI session/message endpoints; four channel contracts with three planned operational adapters and telephony P2 stub; browser mic feasibility; OKF retrieval/grounded FAQ; SQLite read-only haircut availability, multi-turn correction; rules/hosted-LLM intent adapter, Pydantic outputs and 429 fallback; basic LangGraph/tool route and typed UI.

**Deliverables:** reproducible repo and startup instructions, valid source-grounded business-hours answer, synthetic availability response, persisted session, first LLM proof/eligibility note, browser mic/TTS test log, passing initial automated cases.

**Sunday 25 October review:** 3–5 min: start session, show approved business hours with source, read hypothetical availability, inspect session row, show labeled LLM and real voice spike status **PASS/FAIL/BLOCKED**. Evidence: commit IDs, API screenshots, test counts and failures, provider eligibility note. **Milestone:** core typed vertical slice operational; high-risk gates tested early.

### Week 2 | 26 October–1 November — finish P0, begin P1 only when green
**Default:** **26–29 Oct P0 (4 days)**; **30 Oct–1 Nov P1 (3 days)**. **Delay rule:** if P0 unfinished on 29 Oct, use *all three* P1 days as P0 recovery. P0 must be prioritized up to **1 November**.

**P0 work:** complete microphone STT → response → audible TTS; simulated audio-call start/end; bounded context; customer-confirmed handoff queue and protected staff status read; LLM-assisted classification with guards/fallback; persisted outcomes and P0 end-to-end tests. **Early P1 if ahead:** semantic/vector retrieval provider with approved corpus, evidence merge, RAG-empty fallback and initial retrieval tests.

**Deliverables:** working English text/voice/sim-call agent, actual LLM call evidence, three distinct capability demonstrations and real ticket ID visible to authorized staff; optionally first RAG provider tests.

**Sunday 1 November review:** 3–5 min actual microphone and audible TTS; ask a paraphrased question that invokes the hosted LLM, check availability then correct the date; request staff help, explicitly confirm and inspect protected queue; show unauthorized denial and logs. **Milestone:** P0 completed by **29 October target** or **1 November latest**. Never mark speech/LLM complete from fixtures alone.

### Week 3 | 2–8 November — all planned P1 enhancements (7 days)
**Goal:** implement P1 providers without regressing P0. P1 remains optional for minimum assessment, but **every approved P1 epic appears in the backlog with an implementation and test target**.

**Key work:** finalize semantic RAG and OKF fusion, including relevance/conflict tests; Urdu STT → English translation → core → Urdu translation/TTS with preservation of times/ticket IDs; complexity decision and FAQ/booking/support specialized agents; local MCP server/client exposing the same authenticated tools; synthetic booking writes behind safety gate; local CRM profile and advanced ticket transitions; UI, analytics and additional approved FAQ polish.

**Deliverables:** separately switchable P1 adapters, passing feature-specific checks and screenshots/demo traces. **Sunday 8 November review:** compare OKF-only and OKF+RAG evidence; show real Urdu speech if provider supports it, simple tool vs complex agent, local MCP invocation, confirmed synthetic booking and CRM/ticket event; report unverified pieces as blocked, not shipped. **Milestone:** target full P1 completion by **8 November**.

### Week 4 | 9–15 November — finalization, protected P1 extension
**Default:** seven days QA/documentation/demo. **If P1 needs extra time:** use only **9–11/12 November** for priority P1 completion, and reserve **13–15 November** at minimum for final regression, documentation, demonstration and handoff. If P0 had used all of Week 2, P1 scope shrinks by actual capacity; P1 is not allowed to displace mandatory deliverables.

**Key work:** functional/LLM/voice regression; security (staff access, MCP scope, P1 writes); privacy and fake data confirmation; accuracy and retrieval evaluation; fresh separate synthetic November slots for live demo; README, design evidence, user guide, screenshot/video, known limitations, final instructor report and reproducibility audit.

**Sunday 15 November review:** show working live browser demo (text, mic, simulated call), three P0 intents, validated LLM, source evidence, real ticket/status and final test results; showcase **only passing P1 features**; present repository commits, installation instructions, risk log and deviations from plan. **Milestone:** complete, honest, reproducible submission package.

## 4. Resources, tasks, dependencies and tracking

**Planning assumption, not stated personal availability:** 6 focused development hours per calendar day: **66 P0 hours (11 days) + 60 P1 hours (10 days) + 42 finalization hours (7 days) = 168 estimated hours**. Re-estimate actual capacity at each Sunday review. The separate backlog contains task IDs, epics → stories → tasks, daily date allocations, tests, dependencies, criteria and priority. Review burn-up as completed/total P0 stories and completed/total planned P1 stories separately; do not relabel planned P1 as mandatory.

**Definition of Done:** running source code on target hardware; repeatable manual/automated test evidence; expected authorization/failure behavior; linked commit; updated docs. Synthetic demo fixtures and architectural interface diagrams are not implementation evidence.

## 5. Principal risks and contingent responses

| Risk / trigger | Mitigation and honest fallback |
|---|---|
| Hosted LLM unavailable, quota/429, account not eligible | Check official account-specific free allowance early, limit calls and validate schemas; rules/clarify for safe continuity; mark **P0 LLM BLOCKED** until verified and retested |
| Browser STT/TTS unavailable, mic permission denied, Urdu voice absent | Spike first week, test named browser/device and speech vendor/privacy; typed fallback supports usability but does **not** count as voice pass; Urdu P1 may remain unfinished |
| P0 longer than 11 days | Use 30 Oct–1 Nov P1 allocation for P0; move/cut optional P1, retain Week 4 finalization |
| Older 8 GB Windows laptop, slow RAG indexing/agent chains | Keep FastAPI/SQLite native, choose lightweight index and bounded contexts; turn off costly P1 adapters without affecting P0 |
| Unsafe booking/ticket or exposed staff data | Confirmation/authentication, DB transactions/idempotency, server-side tokens, 401/403 tests, audit; keep P1 writes disabled if unsafe |
| Bad RAG evidence, LLM hallucination, Urdu mistranslation | Approved sources/versions only, schema validation, cite evidence, conflict abstention, date/ID roundtrip tests, human confirmation |
| Pinned Oct 19–Nov 1 slots stale at final demo | Keep frozen baseline tests; generate **separate fictional** dated demo slots (never claim real inventory) |
| Lecturer questions three intents or hours unknown | Seek confirmation of three functionally distinct routes; track time as estimate and rebaseline honestly |

## 6. Expected final outcomes and submission evidence

**Minimum demonstrated P0:** automated disclosure; start/end call; real STT/TTS; validated hosted-LLM intent classifier + safe fallback; source-grounded hours FAQ; read-only haircut availability/context; queued ticket ID/protected staff read; logs/tests/README. **P1 targets:** semantic RAG fused with OKF, actual Urdu speech pipeline, specialist agents, local MCP tool exposure, guarded synthetic appointment mutations, local CRM and ticket workflow, enhanced UI/metrics. **Excluded:** Jev, local LLM, Docker, live phone network, paid and external CRM/MCP/helpdesk services.

Submit **this one-month plan Sunday 18 October 2026**. Maintain detailed Agile backlog, daily allocation, weekly review kit, risk/decision audit, source files and synthetic fixtures as implementation evidence. The existence of a plan or dataset is not evidence the software was built. A complete working proof must accompany the final Week 4 review.
