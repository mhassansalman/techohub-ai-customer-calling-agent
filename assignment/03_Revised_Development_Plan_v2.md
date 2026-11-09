# TECHOHUB AI Customer Calling Agent — Revised Development Plan V2

**Revision date:** 8 November 2026  
**Baseline:** `archive/01_One_Month_Development_Plan_v1.md` (18 October 2026); retain V1 unchanged and label **Superseded by V2** in the document index, not “deferred.”  
**Companion execution record:** `04_Revised_Traceable_Backlog_v2.md`  
**Project:** Fictional Demo Salon; FastAPI, SQLite/SQLAlchemy, LangGraph, Groq; React/Vite; Chrome browser STT/TTS  
**Budget objective:** No billed services; no Docker/local LLM required for *development* but Docker now required for *delivery*. Free hosting availability and constraints must be verified at deployment time.

> **Evidence policy:** This is a planning document, not proof of implementation. On 8 November, current source was inspected after the UX08 rollback; the full backend suite passed (270), frontend tests passed (80), frontend production build passed, Python compilation passed, and `git diff --check` passed. No browser was started; real Chrome short-utterance behavior remains unverified.

## 1. Why V2 exists; change control

V1 scheduled P0 for 19–29 October, optional P1 for 30 October–8 November and QA through 15 November. V2 extends P0 customer experience, keeps **RAG** and **minimal specialized agents/local MCP** active, and promotes **Docker plus free public deployment** from previously excluded P2. **Urdu voice (A06–A09) and customer phone identity/OTP (UX08) are deferred** and are not dependencies or acceptance criteria for active work. Existing completed V1 work is inherited, not reset or renumbered. Preserve the V1 files as an immutable historical baseline; update V2 backlog as work proceeds, and amend this plan only when scope, architecture, schedule, risks or acceptance gates materially change.

### Priority labels in V2

- **P0 — Mandatory core + UX stabilization:** Original three-intent working demo, handoff and protected staff API; natural catalog, browsable service UI, seamless Message/Mic/Live switching, browser Call-Only simulation, speech reliability and regression. Customer phone identity/OTP is deferred.
- **P1-S — Selected mandatory advanced scope:** semantic RAG/OKF evidence fusion, minimal specialty-agent delegation, local MCP adapter and tests. These active features retain strict boundaries; Urdu speech work is deferred.
- **P2-S — Selected mandatory delivery scope:** Docker reproducibility and zero-billed public HTTPS deployment with documented persistence policy.
- **Deferred:** Other originally planned P1/P2 items. “Deferred” is an intentional scope decision, not an implementation failure.

## 2. Two customer experiences, one backend

```text
(A) Multimodal browser UI                    (B) Browser Call-Only simulation
    Message ↔ Mic ↔ Live Call                    Speech only, phone-like
    + service cards / controls                   No visual interaction required
                 \                                  /
                  \                                /
                 shared session ID + message history
                              |
                   FastAPI + LangGraph + Groq
                              |
           approved FAQ/OKF + RAG | catalog | slot lookup
                    | handoff | selected agents
                              |
                     existing domain tools
                    (optional local MCP adapter)
                              |
                   SQLite + protected staff API

Later only: actual PSTN/SIP/telephone number via telephony provider (deferred).
```

**Important interface contract:** The three UI modes must be switchable **at any time** while preserving session ID, messages, context, pending handoff and catalog selection where relevant. Switching must safely stop/finish current recognition and TTS, avoid duplicate submissions and respect mic permission. Mic Mode = deliberate single-utterance capture; Live Call = continuous conversational listening; Message = typing. Call-Only is a separate **speech-first experience** in a browser today—not a connected telephone number, not a second AI backend. Accessibility fallback can be offered for failure handling, but normal call-only tasks must not depend on buttons/cards.

## 3. Scope and acceptance gates

| ID / capability | V2 decision | Acceptance gate |
|---|---|---|
| Original P00–P21 foundational P0 | Retain and re-verify | Typed, browser voice, synthetic availability, confirmed queued ticket, staff auth, hosted LLM evidence; regressions pass |
| UX01 catalog path audit + copy | Mandatory P0 | Existing approved catalog/API/response templates inspected; no duplicate price data; natural context-sensitive replies |
| UX02 Browse Services UI | Mandatory P0 | Displays backend-provided service names, price, duration; graceful empty/error state |
| UX03 consistent voice/text/click selection | Mandatory P0 | Three inputs use same backend rules/session; no invented inventory or booking |
| UX04 mode-switch invariants | Mandatory P0 | Message/Mic/Live can switch in any direction, preserve session and pending actions, no double speech or duplicate send |
| UX05 speech-first Call-Only | Mandatory P0 | Voice-only service/FAQ/availability/handoff flow with spoken feedback and end/exit handling |
| UX06 browser voice reliability | Mandatory P0 | Manually test short `yes`, `no`, `ok`, `okay`, recovery, permissions and actual TTS; document browser limitations |
| A00–A05 semantic RAG + OKF | Mandatory P1-S | Approved evidence only; paraphrase recall; dedupe/conflict detection, RAG-empty fallback, provenance and tests |
| A06–A09 Urdu speech pipeline | **Deferred** | No Urdu STT, translation or TTS in the active V2 sequence or its acceptance gates |
| A10–A11 minimal agents | Selected P1-S | Reuse existing FAQ/availability/handoff domain tools; preserve direct fast path, fail-closed on absent agent |
| A12–A13 local MCP | Selected P1-S | One local server/client, typed schemas, restricted tools, timeouts; direct-tool fallback; do not bypass confirmation/auth |
| DEP01 Docker | Mandatory P2-S | Reproducible local build/run, health checks, environment documentation, no secrets in image |
| DEP02 free deployment | Mandatory P2-S | Public HTTPS frontend/backend, real voice demo where browser permits, free-tier constraints documented and durable-vs-disposable storage explicit |
| A14–A15 synthetic booking writes | Deferred | No create/reschedule/cancel; read-only synthetic slot lookup remains P0 |
| A16–A17 CRM/analytics expansion | Deferred | Existing ticket persistence/staff API stays; no advanced CRM promised |
| A18–A19 selected P1 integration scope | Active, limited to selected P1-S | Test RAG, agents and MCP interactions only; exclude Urdu and other deferred features |
| External phone, CRM, booking, helpdesk, remote MCP | Deferred P2 | No claim of phone-number connectivity or real appointments |
| UX08 customer phone identity/OTP | **Deferred** | No customer phone identity, demo OTP, token, or session-ownership work in the active scope |

### Catalog vs appointments

Catalog entries represent **services**, not appointment inventory. Keep the existing P0 **read-only synthetic appointment-slot lookup** operational and accurately labeled. Do not add “catalog doesn't confirm availability” to every service-price answer; only discuss availability/booking limitations when relevant. **Real booking is not implemented.** Sample catalog facts from conversation: haircut $35 / 30 min; beard trim $18 / 20 min; Sunday closed. Verify actual source before using any additional facts.

### Handoff and voice safety invariants

- Only explicit unambiguous consent **in a pending handoff** queues a support ticket; no ticket from incidental `okay`, `yes no`, uncertainty or speech errors.
- Any UI Yes/No button must submit through the normal message API, not directly mutate a ticket.
- Preserve audit records, staff API key protection and idempotency; no real audio storage without a separately approved privacy decision.
- No silent fallback that pretends a failed hosted Groq, MCP call, or live-availability check succeeded.

## 4. Scope boundaries to prevent overbuilding

**Do:** reuse existing sources and domain functions; one local MCP server/client; 2–3 bounded agent roles at most; free-compatible lightweight RAG indexing; small, testable React controls; Dockerized reproducibility; no customer data beyond synthetic demo fixtures.

**Do not:** implement telephone-number calling, paid hosting, production booking CRUD, CRM integrations, remote MCP auth/multi-server discovery, unrelated analytics dashboards, or local LLM installation. Existing direct tools must continue working when RAG, agents or MCP are disabled/unavailable.

## 5. Sequencing and dependencies (revised, not a claim of progress)

| Stage | Work | Dependency | Release evidence |
|---|---|---|---|
| **0 — Inspect/rebaseline** | Confirm Git diff, existing schema, APIs and currently passing tests; record evidence in V2 backlog | Existing repo | Baseline report; no destructive actions |
| **1 — Browser voice reliability** | UX06, then UX07 integration/regression | Existing P0 browser modes | Record real Chrome short-word, permission, silence/recovery and TTS results; no speculative speech changes |
| **2 — Selected RAG** | A00–A05 | Approved knowledge and current APIs | Evidence-fused questions, fallback, conflict handling and tests |
| **3 — Specialized agents** | A10–A11 | Stable domain tools and RAG | Direct fast path and bounded agents using existing capabilities |
| **4 — Local MCP** | A12–A13 | Approved, guarded domain tools | Typed schemas, access controls, timeout/fallback and safety tests |
| **5 — Deployment** | DEP00–DEP04 | Active P0/P1 sequence; security gate below | Docker, hosting/persistence decision and documented limitations |
| **6 — Final QA** | F00–F06 adapted to active scope | Above | Fresh test evidence, demonstration, security/privacy and known limitations |

**Dates:** The original 15 November 2026 submission date is the **V1 baseline**, not automatically a feasible new commitment. V2 is dated 7 November. Re-estimate actual effort and obtain a new delivery date if 15 November is not fixed; if it *is* fixed, treat time-boxed feature cuts as an explicit scope change, **never** silently mark untested mandatory items complete. Protect final regression and documentation time.

## 6. Deployment decision gates

- **Docker locally:** backend image and sensible frontend serving/deployment plan; deterministic build; documented run commands; health endpoint; environment/secret examples. Verify whether bundling services in one image or splitting them is supported by the chosen host.
- **Free cloud:** verify current free tier, supported regions/runtime, sleeping behavior, outbound access, WebSocket/HTTP support if needed, CPU/RAM/storage limits, account requirements and quota. No provider is committed in V2 until tested.
- **Data:** SQLite on ephemeral container storage is **not durable**. Either choose a truly free persistent data option and test restart survival, or use explicitly disposable sample data and acknowledge that newly created tickets/sessions may be lost after restarts. Never claim durable support ticket persistence without evidence.
- **Browser voice:** Chrome Web Speech APIs depend on browser/microphone/service compatibility and may behave differently in hosted environments. HTTPS is required for normal mic permission behavior; verify actual audible interaction.
- **Reproducibility:** README setup, exact environment variables, no hardcoded keys, smoke tests, health checks, logs and limits.

## 7. QA and Definition of Done

**Each task:** code implemented in working tree; focused tests pass; relevant integration tests pass; browser/live-provider evidence for active voice/Groq/deployment scope; safety tests; recorded commit/hash if committed; docs updated. Test reports from an external assistant are **Reported**, not independently verified until reviewed. Where a result is not proven, use `Needs verification` or `Blocked`—not `Done`.

**Mandatory scenario set:** service question by text and voice; catalog UI select; Message→Mic→Live→Message with same session; Call-Only without clicking; single-word handoff yes/no/okay + mixed-response safety; synthetic appointment read-only check; hosted LLM invocation; OKF/RAG fuse/fallback/conflict; agents with MCP on/off and safe handoff; Docker local cold start; deployed HTTPS mic/TTS and storage restart behavior. Urdu roundtrip and customer identity/OTP are deferred.

## 8. Risk and response

| Risk | Response |
|---|---|
| Chrome short words still missed | Investigate actual result/error lifecycle and mic permissions; capture manual browser evidence; support typed/visible confirmation in multimodal UI; do not call voice fixed without test |
| More scope than available time | Complete UX06 → UX07 → RAG → specialized agents → MCP → deployment; document any explicit changes to selected scope |
| Inconsistent catalog and UI | Single backend source of truth; no frontend hardcoded prices |
| Unsafe booking or handoff | Read-only availability; pending confirmation, idempotency, protected staff operations |
| RAG hallucinations or conflict | Only approved source material, citation/evidence provenance, abstain on conflict |
| Free tier sleep/ephemeral disk | Document impact, choose persistent storage or label demo disposable, test cold starts |
| Feature names imply real phone network | Call-Only explicitly browser simulation; telephony remains deferred |
| Anonymous customer session APIs use the session ID as the only practical access boundary | Session IDs are not customer authentication. Before public deployment, implement and verify an approved ownership/authentication design or keep session APIs private/restricted; do not describe the current API as customer-authenticated. UX08 remains deferred and must be explicitly re-approved before implementation. |

## 9. Progress and governance

- **V1:** freeze. Never rewrite its task history.
- **V2 backlog:** update after each meaningful task with `Status`, `Evidence`, `Date`, `Notes/Blockers`; keep immutable IDs for inherited items.
- **V2 plan:** update only at scope, architectural, risk or milestone decision points; add revision note below.
- **Review cadence:** after UX06/UX07, after RAG, after specialized agents/MCP, and after live deployment. Report automated and human/browser checks separately.

### V2 revision log

| Date | Version | Decision |
|---|---|---|
| 2026-11-07 | 2.0 | Rebaseline original P0/P1/P2 into extended P0, selected mandatory P1 and selected mandatory P2 deployment; preserve V1 baseline |
| 2026-11-08 | 2.1 | Defer UX08 customer phone identity/OTP and A06–A09 Urdu speech; sequence active work UX06 → UX07 → RAG → specialized agents → MCP → deployment; record public anonymous-session access as a release risk |
| 2026-11-09 | 2.2 | Re-verified no UX08/OTP/auth code remains in any backend or frontend file; confirmed UX00–UX05 unaffected; fresh test baseline: backend 270 passed, frontend 80 passed, build/compile/diff-check clean; active sequence and deferred scope unchanged |
| 2026-11-09 | 2.3 | Completed automated UX07 regression (backend 271 passed, frontend 93 passed, build clean); confirmed anonymous session API access boundary risk as DEP04 gate; active queue proceeds to RAG (A00–A05) |
