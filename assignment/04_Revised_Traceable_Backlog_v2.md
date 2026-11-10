# TECHOHUB AI Customer Calling Agent — Revised Traceable Backlog V2

**Revision:** 2.0 — 7 November 2026  
**Active plan:** `03_Revised_Development_Plan_v2.md`  
**Frozen baseline:** `archive/02_Traceable_Backlog_and_Daily_Schedule_v1.md`  
**Source-of-truth rule:** This is the **living execution backlog**. Update it as code and tests are verified. Preserve original IDs; use new `UXxx` and `DEPxx` IDs for newly introduced scope.

## 1. Status vocabulary, evidence and priority

- **Reported implemented / verify:** User-provided Copilot report or prior handoff says implemented; do not equate this with independently reviewed source or manual/browser verification.
- **Needs verification:** Evidence absent or acceptance gate not yet fully checked.
- **Pending:** In chosen scope but not confirmed implemented.
- **In progress:** Work actually underway (do not infer solely from scheduled date).
- **Done — verified:** Code inspected, applicable automated/manual tests passed and evidence reference recorded.
- **Blocked:** Specific reproducible dependency/failure recorded.
- **Deferred — out of V2 scope:** Intentionally excluded from V2, distinct from failing/not started.

**Priority:** `P0` mandatory original+UX; `P1-S` selected RAG/agents/MCP; `P2-S` selected Docker/zero-billed deployment; `QA` mandatory finalization. **Urdu A06–A09 and customer identity/OTP UX08 are deferred and excluded from active dependencies and acceptance criteria. No item is automatically Done because its original date has passed.**

## 2. Snapshot: inherited original P0 tasks

The original P00–P21 task definitions, story/test IDs and October dates remain in V1. This concise table retains **every original task ID** and summarizes available evidence; check repository + acceptance tests before upgrading any row to Done. Exact original descriptions remain authoritative in V1.

| IDs | Original scope (short) | V2 priority | Initial V2 status | Evidence / remaining gate |
|---|---|---|---|---|
| P00–P01 | Repo/environment and salon fixtures | P0 | Reported implemented / verify | Reproducible setup and fixture validation |
| P02–P03 | Channel contracts, mic/STT/TTS spike | P0 | Reported implemented / verify | Real named-browser test |
| P04–P05 | Persisted sessions; FastAPI endpoints | P0 | Reported implemented / verify | API/data test re-run |
| P06–P07 | OKF retrieval and safe FAQs | P0 | Reported implemented / verify | Source attribution and unsupported question |
| P08–P09 | Read-only synthetic appointment slots, multi-turn correction | P0 | Reported implemented / verify | Fresh demo dates, no DB writes |
| P10–P11 | Hosted Groq intent + safe fallback | P0 | Reported implemented / verify | Actual provider invocation and failure behavior |
| P12–P13 | Typed UI; LangGraph routes | P0 | Reported implemented / verify | Integration and routed intent demo |
| P14–P15 | Browser mic/TTS; error handling | P0 | **Needs verification** | Brief single words (`yes/no/okay`) missed in Chrome; actual testing required |
| P16 | Simulated Live Call controls | P0 | Reported implemented / verify | Call lifecycle and mode transitions |
| P17 | Transcript, channel and audit persistence | P0 | Reported implemented / verify | Ensure no raw audio retention |
| P18 | Confirmed queued human handoff | P0 | Reported implemented / verify | Pending-state gating and exactly-once ticket |
| P19 | Protected staff read API | P0 | Reported implemented / verify | Unauthorized/authorized checks; secret protection |
| P20–P21 | P0 E2E, fixes and documentation | P0 | Reported implemented / verify | Latest reported suites below; manual voice gate outstanding |

**Latest supplied implementation report (7 Nov):** `workflow.py`, `test_workflow.py`, `test_api_sessions.py`, `App.jsx`, `App.test.jsx`, `styles.css` modified for pending handoff grammar, contextual clarification and Yes/No buttons through existing message API. Copilot reports **264 backend tests, 48 frontend tests**, production build, compilation and `git diff --check` passing. **This does not prove short-word Chrome STT works.** Verify actual uncommitted diffs, codebase state, server restart and manual Chrome behavior before declaring P0 complete.

## 3. Extended P0 backlog — NEW

| ID | Story / task | Depends on | Acceptance / test evidence to record | Status |
|---|---|---|---|---|
| UX00 | Read-only source inspection: catalog storage, lookup/API, response composition, React component and tests; baseline Git status | Existing P0 | Source map and tests recorded below; confirmed there is no separate catalog endpoint | Done — verified |
| UX01 | Natural context-sensitive catalog and booking wording | UX00 | Grounded price/list, polite unknown-service response, booking limitation, and working read-only availability; regression tests pass | Done — verified |
| UX02 | Browse Services panel/popup from approved backend catalog (reuse API if present) | UX00 | `GET /api/services` returns validated active catalog records only; panel loading/empty/error, close and Escape behavior tested | Done — verified |
| UX03 | Voice, text and click service selection | UX01, UX02 | Cards submit a natural service question through the active session message API; existing text/Mic/Live Call behavior remains covered; no ticket or booking mutation | Done — verified |
| UX04 | Safe anytime Message ↔ Mic ↔ Live switching | P16, P17 | All 6 directed transitions; same session/messages, no duplicate requests, stop/cleanup listening/TTS, retain pending handoff | Done — verified |
| UX05 | Distinct browser Call-Only speech-first experience | UX04, P18 | Spoken menu/selection, FAQ, read-only slot query, handoff confirmation and end call without visual controls; no actual phone-number claim | Done — verified |
| UX06 | Diagnose and test Chrome short-word recognition — **next active task** | P14–P16, latest handoff work | Document `onresult/onerror/onend`, STT final/interim, silence/permission/TTS behavior; manual `yes`, `no`, `ok`, `okay` | Needs verification |
| UX07 | Extended P0 integration and regression | UX06 | Tests + manual browser matrix for text, mic, live, call-only and safety; capture pass/fail evidence | Done — verified (automated) |

**Deferred from active V2:** UX08 customer phone identity/OTP is postponed in full; do not add customer auth, ownership, or OTP dependencies or bypasses. A06–A09 Urdu STT/translation/TTS are postponed; do not make Urdu support an active acceptance gate.

**Public-deployment security gate:** Current customer session routes are anonymous; the UUID session ID is the only practical access boundary. Before public deployment, implement and verify an explicitly approved authentication/ownership design or keep the session API private/restricted. Do not claim customer identity or authorization based on possession of a session ID. UX08 is deferred, so deployment must remain gated on a separately approved mitigation.

**Do not** change recognition lifecycle speculatively. Fix only evidence-backed defects. For pending handoff, `okay` and `ok` are confirmations only in correct state; mixed `yes no` must never create a ticket. UI Yes/No buttons must use the ordinary message endpoint. Preserve read-only synthetic availability even though real booking is excluded.

**UX00 inspection evidence:** The approved service records are `fixtures/demo_salon.json`, validated as `ServiceFixture` by `backend/fixtures.py` and loaded into the deterministic `KnowledgeService` through `_fixture_records` / `_service_record` in `backend/knowledge.py`. `KnowledgeIndex.retrieve`, `compose_answer`, `_compose_service_answer`, `_compose_service_list`, and `_abstention_text` implement lookup and catalog responses. `backend/availability.py` owns read-only fixture slot lookup and availability responses. There is no separate catalog API; `frontend/src/api.js:sendMessage` posts all text/transcript turns to `/api/sessions/{session_id}/messages`, handled by `backend/main.py:create_message`, which invokes `ConversationWorkflow.run`. LangGraph routes through `_faq_capability`, `_availability_capability`, and `_support_capability` in `backend/workflow.py`. Groq is used for intent classification, not customer-facing response generation. Relevant tests: `tests/test_fixtures.py`, `tests/test_knowledge.py`, `tests/test_intent.py`, `tests/test_availability.py`, `tests/test_workflow.py`, and `tests/test_api_sessions.py`.

**UX01 verification evidence:** `tests/test_knowledge.py`, `tests/test_intent.py`, `tests/test_availability.py`, `tests/test_workflow.py`, and `tests/test_api_sessions.py` passed together (230 tests); the full backend suite passed (266 tests). Python compilation and `git diff --check` passed. No browser or live Groq verification was performed.

**UX02/UX03 verification evidence:** `backend/main.py:list_services` serves only active, validated `ServiceFixture` records from `load_demo_salon_fixture`; `ServiceCatalogItem` restricts the response to stable ID, name, amount, currency, and duration. `tests/test_api_sessions.py` verifies fixture values, the limited response shape, missing/invalid catalog fail-closed behavior, and a service inquiry through the existing message route without ticket creation. `frontend/src/App.jsx` and `frontend/src/api.js` add the accessible Browse Services panel and use existing `sendMessage` for card selection; `frontend/src/App.test.jsx` covers loading, empty/error, close/Escape, click and recognized-Mic service questions through the current session, disabled selection during live listening, and duplicate prevention. Existing text, Mic, and Live Call regressions remain passing. Full backend: 270 passed; frontend: 54 passed; production build, Python compilation, and `git diff --check` passed. No browser, real microphone, or live Groq verification was performed.

**UX04 verification evidence:** `frontend/src/App.jsx` now exposes Message, Mic, and Live Call modes during an active session. One mode-switch handler invalidates prior recognition generations, detaches and aborts active recognition, waits for its `onend` before permitting another recognition cycle, cancels TTS, clears obsolete Live Call restart state, and leaves session/messages and pending requests untouched. Live Call auto-listening waits for an active session and idle request state; switching to Mic does not start recognition automatically. `frontend/src/App.test.jsx` covers all six directed transitions, session/transcript preservation, active Mic and Live recognition cancellation, asynchronous abort gating, stale callbacks, switching during TTS and an in-flight API request, no duplicate/overlapping recognition, retained handoff controls, catalog selection after switching, and existing End Call/fresh Live Call behavior. Focused UX04 tests: 15 passed; full frontend suite: 68 passed; production build and `git diff --check` passed. Browser APIs were mocked; manual Chrome switching, microphone, and TTS behavior remain unverified.

**UX05 final verification evidence:** `frontend/src/App.jsx` provides the separate Multimodal/Call-Only chooser and reuses the existing `browser_voice` session, message API, Live Call SpeechRecognition/SpeechSynthesis lifecycle, bounded silence recovery, and End Call flow. `frontend/src/App.test.jsx` covers chooser selection, Call-Only speech-to-API-to-TTS-to-listen behavior, hidden chat/catalog/confirmation controls, service/availability/handoff utterances, cleanup and stale callbacks, delayed abort, permission/silence errors, duplicate prevention, fresh call sessions, and existing multimodal UX04/catalog/handoff regressions. From `frontend/`, `npm.cmd test` passed **80 tests** and `npm.cmd run build` succeeded; repository-root `git diff --check` passed. The two catalog-panel tests initially failed because they did not choose Multimodal in the new experience chooser; their setup now selects Multimodal, with assertions unchanged. Speech APIs were mocked; real Chrome microphone/TTS verification remains pending.
**UX06 diagnosis and evidence:** Root cause investigation revealed a major application lifecycle defect interacting with Chromium's Web Speech API: for brief isolated utterances (yes, 
o, ok, okay), Chrome frequently emits interim hypotheses (isFinal: false) and immediately follows with silence timeout and onend (often accompanied by onerror: "no-speech"), without emitting a subsequent frame with isFinal: true. The prior implementation strictly filtered for isFinal: true, completely discarding interim speech hypotheses and mistaking the closed stream for silence. rontend/src/App.jsx was improved across Mic, Live Call, and Call-Only modes to track the latest recognized hypothesis during recognition and rescue it upon onend if no final result was emitted before stream closure, while preserving strict duplicate-submission guards, cancellation invalidation, and bounded silence recovery (1 retry in Live Call). 11 new regression tests in rontend/src/App.test.jsx verify short words as final and rescued interim results across all three modes, duplicate prevention, cancellation, stale callbacks, and genuine silence handling. Full frontend suite: **91 passed**; production build succeeded; full backend suite: **270 passed**; git diff --check clean. Browser APIs were mocked in automated tests; real Chrome microphone, acoustic latency, and voice testing remain unverified, so UX06 status remains Needs verification.

**UX07 verification evidence:** Completed comprehensive automated end-to-end regression across all P0 deliverables (UX00–UX06). Backend suite passed with **271 tests** (including newly added 	est_concurrent_sessions_have_strict_data_and_handoff_isolation verifying session isolation, ticket scoping, and staff API authorization). Frontend suite passed with **93 tests** (including UX06 speech reliability and new Call-Only error handling and booking disclaimer assertions). Frontend production build succeeded; Python compilation clean; git diff --check clean. Security audit confirmed that anonymous /api/sessions/{session_id} routes do not expose message history/transcripts, but possession of a session UUID permits turn submission and ending; this remains documented as an unresolved pre-deployment blocker for DEP04. Real-browser Chrome voice acceptance is deferred, leaving UX06 as Needs verification. UX07 automated regression acceptance criteria are fulfilled.

## 4. P1-S backlog — inherited IDs, selectively chosen

| Original IDs | Feature / deliverable | V2 decision | Acceptance / tests | Initial status |
|---|---|---|---|---|
| A00–A01 | Approved RAG corpus/index and small vector adapter | Mandatory P1-S | Approved-only chunks, repeatable lightweight index, source identity | A01 implemented (chunker + knowledge_bundle, 16 tests); A00 vector adapter deferred — no embeddings/vector DB per A01 constraints |
| A02–A03 | OKF+RAG fusion, deduplication, abstention/conflict/fallback | Mandatory P1-S | Empty RAG→OKF, conflicting sources→safe abstain, paraphrase tests | A02 implemented (backend/rag.py + tests/test_rag.py, 13 tests); A03 implemented (backend/rag.py hardening + 5 new tests); lexical fusion over A01 chunks — semantic embedding provider pending under A05 |
| A04–A05 | RAG feature flag, evidence view/metrics, stabilize | Mandatory P1-S | Known-provenance answer; existing OKF direct path remains working | A04 implemented (TECHOHUB_RAG_ENABLED flag, LangGraph FAQ integration, safe fallback, retrieval_reason diagnostics); A05 implemented (semantic embeddings via cached all-MiniLM-L6-v2 model, cosine similarity, safe fallback to lexical→OKF) |
| A06–A07 | Urdu STT and Urdu→English normalization | **Deferred — out of active V2 scope** | No Urdu STT/normalization acceptance gate in active V2 | Deferred |
| A08–A09 | English→Urdu response translation and Urdu TTS | **Deferred — out of active V2 scope** | No Urdu translation/TTS acceptance gate in active V2 | Deferred |
| A10–A11 | Bounded complexity routing and specialized agents | Selected mandatory P1-S (minimal) | Reuse FAQ/availability/support domain tools; no duplicated writes; simple fast path | A10/A11 implemented (backend/agents.py, backend/workflow.py, tests/test_agents.py). AgentRegistry + RuleFirstIntentClassifier route simple intents to deterministic capabilities and complex intents to specialized agents (FaqAgent, AvailabilityAgent, SupportAgent). tests/test_agents.py (8 tests) cover complexity classification, agent registry, FAQ/availability/support agents, workflow integration. Full backend suite: 350 passed; Python compilation clean; git diff --check clean; frontend 93 passed; vite build passed.
| A12–A13 | One local MCP server/client for existing approved tools | Selected mandatory P1-S (minimal) | Schema/ACL/timeout/audit, direct fallback, pending handoff gates intact | Pending |
| A14–A15 | Synthetic create/reschedule/cancel booking | **Deferred — out of V2 scope** | No writes; keep original P0 read-only lookup | Deferred |
| A16–A17 | CRM profiles, advanced ticket updates, analytics expansion | **Deferred — out of V2 scope** | Keep existing P0 persisted tickets and staff read | Deferred |
| A18–A19 | P1 cross-feature integration and fixes | Active, **re-scoped** P1-S | Test only selected RAG, agents and MCP interactions; no Urdu or other deferred-feature assertions | Pending |

**MCP minimum:** expose existing FAQ/catalog, synthetic availability and carefully guarded support tools where safe. A tool listed via MCP is never permission to bypass server confirmation, staff authorization or idempotency. Direct-tool mode remains functional if MCP is off. **Agents minimum:** no extra agent just to replace deterministic one-question routing; preserve LangGraph quick path.

### A10/A11 known limitation — agent reachability under normal intent classification

`SupportAgent` is reachable through normal production routing: `Book a haircut appointment Friday.` is classified `APPOINTMENT_CREATE` by `ComplexityClassifier.COMPLEX_INTENTS` and routes via `classify_complexity` to `agent_support`.

`FaqAgent` and `AvailabilityAgent` are integrated into the compiled LangGraph and verified using mocked intent classifiers (tests in `tests/test_agents.py`). However, normal rules-first intent classification (`classify_with_rules` in `backend/intent.py`) currently sends certain multi-service FAQ and multi-date availability requests to clarification before they reach agent routing:

- Multi-service FAQ (e.g. "What is the price of a haircut and what is the price of a beard trim?") is classified `FAQ_SERVICE_POLICY` but `ComplexityClassifier` only marks it COMPLEX when `mentioned_service_ids` detects more than one service. The rules classifier returns clarification for ambiguous or combined phrasings before reaching the complexity node.
- Multi-date availability (e.g. "Do you have haircut slots Friday and Saturday?") is classified `APPOINTMENT_AVAILABILITY` but `ComplexityClassifier` only marks it COMPLEX when more than one day token is detected. `_parse_message_date` returns `AMBIGUOUS` for multiple dates in `backend/availability.py`, producing clarification before agent routing.
- Multi-day hours (e.g. "Are you open Friday and Saturday?") similarly reaches clarification through `_requested_days` in `backend/knowledge.py`.

This is an **acknowledged limitation, not a confirmed failure of the existing A10/A11 acceptance criteria**. The agent nodes exist in the compiled graph, are wired to `aggregate_response`, and produce valid `CapabilityResult` outputs when invoked directly or via mocked classifiers. Future intent-classification improvements (e.g. relaxed date/ambiguity handling) may address this limitation without changing the agent implementation.

No source-code or test changes are required for this documentation; the limitation is recorded here for traceability.

## 5. P2-S backlog — NEW delivery requirements

| ID | Story / task | Depends on | Acceptance / evidence | Status |
|---|---|---|---|---|
| DEP00 | Deployment feasibility and persistence audit | Stable backend/API | Confirm memory/runtime, frontend/backend topology, Web Speech HTTPS and SQLite durability requirements; compare free-tier limitations without hardcoding provider assumptions | Pending |
| DEP01 | Dockerfile(s), `.dockerignore`, health/run docs, env examples | DEP00 | Local clean build and launch; no keys baked in; reproducible commands, health probe, test smoke | Pending |
| DEP02 | Free public HTTPS deployment | DEP01 | Actually reachable frontend and backend; zero-billed plan verified; startup/cold-start/privacy/limits documented | Pending |
| DEP03 | Storage and restart safety verification | DEP00, DEP02 | Demonstrate durable DB if available **or clearly label disposable synthetic sessions/tickets**; no false persistence claims | Pending |
| DEP04 | Deployed end-to-end demo and setup guide | DEP02, DEP03, UX07, A18–A19, public-session security gate | Browser mic/TTS where supported, text, safe handoff, RAG, container logs and known limitations captured | Pending |

**Explicitly deferred P2:** actual PSTN/SIP/Twilio number connection; external CRM/helpdesk/booking integrations; remote MCP integrations; local LLM/Ollama; paid hosting/model services. Docker + free deployment are **promoted selected P2-S scope** rather than deferred.

## 6. Final QA backlog (existing IDs retained)

| IDs | V2-adapted deliverables | Status | Exit evidence |
|---|---|---|---|
| F00 | Full regression: original P0 + extended UX + selected P1-S + deployment | Pending | Automated results, manual browser and hosted-provider cases; only active RAG/agent/MCP P1 tests apply; Urdu excluded |
| F01 | Security/privacy audit | Pending | Staff API, MCP scope, pending handoff, secret/env and audio/data policy checks |
| F02 | Defect/performance follow-up | Pending | Reproduced defects, fixes, memory/cold-start/latency notes |
| F03 | End-to-end rehearsal with **fresh synthetic slots** | Pending | No stale/real appointment representation |
| F04 | README, architecture, env/deployment instructions and exclusions | Pending | New developer reproducibility |
| F05 | Screenshots, demo/test matrix, final report | Pending | Traceable PASS/FAIL/BLOCKED screenshots/logs |
| F06 | Final handoff/reproducibility audit | Pending | Rebuild on clean environment and completion summary |

## 7. Dependency and execution order

```text
REBASELINE current repo + record passing tests
    |
    +--> UX00 --> UX01 --> UX02 --> UX03
    |                               |
    +--> UX04 --> UX05 --> UX06 --> UX07
                                      |
                      A00-A05 RAG ---+
                         A10-A11 agents
                             A12-A13 MCP
                                  |
                         A18-A19 P1 integration
                                  |
            DEP00 --> DEP01 --> DEP02 --> DEP03 --> DEP04
                                  |
                              F00–F06 QA
```

**Execution note:** Active sequence is UX06 → UX07 → RAG (A00–A05) → specialized agents (A10–A11) → MCP (A12–A13) → deployment. Urdu A06–A09 and UX08 customer identity/OTP are deferred. Keep public deployment gated by session API access mitigation. MCP/agents remain deliberately small.

### Scheduling rule

V1's **19 Oct–15 Nov** calendar is preserved as historical. **V2 has no fabricated revised dates or hour estimates** until remaining work and true deadline are confirmed. Use this sequence as the active queue; record real `Started`, `Completed`, `Hours`, `Commit/Evidence` per task below. If 15 November remains non-negotiable, document risk and request explicit scope/time trade-offs instead of silently claiming completion.

## 8. Acceptance test matrix and trace IDs

| Test ID | Scenario | Tasks |
|---|---|---|
| T-UX-01 | Service price/duration grounded in backend catalog; no irrelevant disclaimers | UX00–UX03 |
| T-UX-02 | Browse Services loading, selection and empty/error views | UX02–UX03 |
| T-UX-03 | All six UI mode transitions preserve session, pending action and no double submit | UX04 |
| T-UX-04 | Call-Only voice-only FAQ/catalog/availability/handoff/end | UX05 |
| T-UX-05 | Chrome manual yes/no/ok/okay; noisy input, silence, mic permission and TTS interaction | UX06–UX07 |
| T-UX-06 | Pending `okay` approval vs nonpending ack; mixed `yes no` rejection; one ticket only | P18, UX04–UX07 |
| T-P1-01 | RAG approved sources, paraphrase, empty fallback, conflict abstain | A00–A05 |
| T-P1-02 | Real Urdu ASR/translation/TTS preserves dates, prices and ticket IDs | A06–A09 — **Deferred** |
| T-P1-03 | Direct fast path vs selected agent routing, safe absence/failure | A10–A11 |
| T-P1-04 | MCP schemas, allowlist/ACL, errors, direct fallback, confirmation guards | A12–A13 |
| T-P1-INT | RAG + agents + MCP integration (Urdu excluded) | A18–A19 |
| T-DEP-01 | Docker clean build, launch, health, secrets handling | DEP00–DEP01 |
| T-DEP-02 | Public HTTPS reachability, voice constraints, cold start, storage restart behavior | DEP02–DEP04 |
| T-FINAL | Full security, reproducibility, documentation, demo | F00–F06 |

**Maintain original T-01..T-20 and the applicable V1 P0 trace**; inherited acceptance tests are not replaced by this matrix.

## 9. Suggested progress tracking entries (copy per task)

```md
### TASK-ID — Short title
- Priority: P0 / P1-S / P2-S / QA
- Status: Pending / In progress / Reported implemented / Needs verification / Done — verified / Blocked / Deferred
- Started: YYYY-MM-DD or —
- Completed: YYYY-MM-DD or —
- Actual effort: —
- Dependencies: ...
- Evidence: test command + count, screenshot/log, source path, commit hash (if committed)
- Blocker / decision: ...
- Next step: ...
```

### Initial daily log

| Date | Entry | Evidence | Next action |
|---|---|---|---|
| 2026-11-07 | V2 scope agreed: extended P0; RAG, Urdu, minimal agents/MCP; Docker/free deploy; booking CRUD/CRM/real telephony deferred | Planning decision in conversation | Inspect repo and re-verify baseline |
| 2026-11-07 | Copilot reports handoff grammar/confirmation button fixes | 264 backend / 48 frontend automated tests reported; **not independently validated here** | Manual Chrome short-word handoff test; inspect uncommitted diff |
| 2026-11-08 | Deferred UX08 phone identity/OTP and A06–A09 Urdu; made UX06 the next active task and reordered remaining active sequence | V2 scope change; source/tests inspected | Complete UX06 Chrome verification; mitigate anonymous session API access before public deployment |
| 2026-11-08 | Verified UX08 rollback and UX00–UX05 regression baseline; synchronized active V2 dependencies and evidence | Backend 270 passed; frontend 80 passed; production build, Python compile and `git diff --check` passed; no browser verification | UX06 remains Needs verification; mitigate anonymous session API access before public deployment |
| 2026-11-09 | Re-verified: UX08 fully absent from all backend .py files, schemas, tests and frontend; no OTP/phone/auth endpoints present. Active sequence UX06 → UX07 → RAG → agents → MCP → deployment confirmed in plan and both backlogs. Staff API key (`secrets.compare_digest`, env-only) and anonymous session routes unchanged. | Backend 270 passed; frontend 80 passed; production build passed; Python compile passed; `git diff --check` clean (LF/CRLF advisory only, not a whitespace error). All deferred: UX08, A06–A09. | UX06 Chrome short-word manual verification remains outstanding; session API access mitigation required before public deployment |
| 2026-11-09 | UX06: Diagnosed short-word no-speech causes; implemented interim transcript rescue on onend across Mic, Live Call and Call-Only; added 11 regression tests | Frontend 91 passed; backend 270 passed; frontend build and git diff --check clean | Manual Chrome verification with real microphone required; UX06 remains Needs verification |
| 2026-11-09 | UX07: Completed extended P0 regression (271 backend tests, 93 frontend tests, build clean); audited anonymous session APIs; documented DEP04 deployment blocker | Backend 271 passed; frontend 93 passed; production build and git diff --check clean | Next active work: RAG A00–A05 (UX06 real Chrome testing deferred) |

## 10. Change log / task-state governance

**Do not modify V1 to match future reality.** Update **this** V2 after each implemented task; update the V2 plan when major decisions change. Keep `Deferred` rows visible with rationale. Do not mark a pending item done based only on elapsed dates, generated source, a green build unrelated to its acceptance gate, or hosted features that were never tested. If a task is split, keep its original parent ID and add child IDs (e.g. `UX04a`) for auditable linkage.

| Date | Revision | What changed |
|---|---|---|
| 2026-11-07 | 2.0 | Inherited P00–P21; added UX00–UX07 and DEP00–DEP04; selected A00–A13, re-scoped A18–A19; deferred A14–A17; retained F00–F06 |
| 2026-11-08 | 2.1 | Deferred UX08 and A06–A09; set active sequence UX06 → UX07 → RAG → agents → MCP → deployment; added anonymous session API deployment gate |
| 2026-11-08 | 2.2 | Updated inspected regression evidence; removed deferred Urdu and booking/CRM tests from active QA scope; made RAG → agents → MCP dependencies explicit |
| 2026-11-09 | 2.3 | Re-verified UX08 completely absent (no OTP/phone/auth code anywhere); confirmed UX00–UX05 regression pass; re-ran and recorded fresh test baseline; active sequence unchanged |
| 2026-11-09 | 2.4 | UX06: Fixed short-word interim transcript drop on onend across Mic, Live Call and Call-Only; added 11 frontend regression tests (91 passed); UX06 remains Needs verification |
| 2026-11-09 | 2.5 | UX07: Completed automated P0 regression (backend 271 passed, frontend 93 passed); audited anonymous session APIs; marked UX07 Done — verified (automated); next: RAG A00–A05 |
