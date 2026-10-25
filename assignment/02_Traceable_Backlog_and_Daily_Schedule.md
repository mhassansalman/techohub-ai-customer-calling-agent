# Traceable Agile Backlog — P0 + ALL Planned P1 Enhancements

**Capacity assumption:** six focused hours per calendar day for estimation only; actual personal availability has **not** been provided. **Default:** 66h P0 / 60h P1 / 42h QA. Each task below is a 3-hour package (QA 6h). **If P0 slips**: Oct 30–Nov 1 become P0 recovery, superseding the P1 tasks assigned there; replan P1 priorities and, only if necessary, use Nov 9–11/12. **Priority remains P1**, never P0 because it was scheduled.

## Epic → user story → acceptance trace

| Epic | Tier | Story IDs and outcomes | Acceptance criterion / Definition of Done | Tests |
|---|---|---|---|---|
| E0-01 Platform, sessions and persistence | P0 | S0-01 initial repo/fixture; S0-03 session API | P0 app starts and messages/outcomes persist | T-01 T-08 |
| E0-02 Channels and actual voice | P0 | S0-02 four contracts/spike; S0-08 browser voice; S0-09 simulated call | Real mic/STT/TTS and simulated-call lifecycle; typed fallback | T-10 T-11 |
| E0-03 Hosted LLM intent | P0 | S0-06 eligible-free classifier and fallback | Real model call + allowlist classification, rate-limit safety | T-12 |
| E0-04 Approved knowledge | P0 | S0-04 OKF retrieval/grounded reply | Source ID and unknown-source abstain | T-02 T-03 |
| E0-05 Availability | P0 | S0-05 read-only slot lookup & context | Correct slot and date follow-up; no write | T-04 T-05 |
| E0-06 Support ticket | P0 | S0-10 confirmed ticket+protected staff | True queued ID visible to authorized staff only | T-19 T-20 |
| E0-07 Orchestration/test hardening | P0 | S0-07 LangGraph UI; S0-11 E2E | Three routes work and pass regression | T-01..T-12 |
| E1-01 Semantic RAG / evidence | P1 | S1-01 index; S1-02 fusion/fallback | OKF alone and OKF+RAG correct; conflicts abstain | T-P1-01 |
| E1-02 Urdu voice pipeline | P1 | S1-03 incoming Urdu; S1-04 outgoing Urdu | Actual Urdu ASR, translate, Urdu audio, ID/time fidelity | T-P1-02 |
| E1-03 Specialized agents | P1 | S1-05 complexity, FAQ/booking/support | Simple direct path; complex agent; absent-agent safe path | T-P1-03 |
| E1-04 Local MCP tools | P1 | S1-06 local server/client, validation | Typed MCP calls/ACLs; direct tool works with MCP off | T-P1-04 |
| E1-05 Guarded booking operations | P1 | S1-07 synthetic bookings/migrations | Customer auth, confirmation, atomicity/idempotency | T-P1-05 |
| E1-06 CRM, support and UX | P1 | S1-08 local CRM/ticket updates; S1-09 cross-feature | Fake customer access control, lifecycle audit, metrics | T-P1-06 |
| EF-01 Regression, safety and performance | QA | SF-01–SF-03 regression/security/performance | Test suite and documented fixes with reproducibility | T-01..T-P1-06 |
| EF-02 Final delivery and review | QA | SF-04–SF-07 demo/report/packaging | README/report/screenshots/live demo and known limitations | T-01..T-P1-06 |

### Story structure and done policy
Every `S0-xx`, `S1-xx` or `SF-xx` is a user/developer story under the epic shown in the dated daily schedule. **As a salon customer**, I need correct voice/text routing, knowledge, availability and support so that I receive an accurate response. **As a developer/operator**, I need tests, authorized records, observable failures and incremental integration so that the system is safe and reproducible. P1 stories add semantic questions, Urdu conversations, complex agent selection, local MCP access and confirmed booking; test IDs linked below are their checkable acceptance scenarios. A task is only done after implementation, passing tests, commit and evidence; design fixtures do not count.

## Daily execution schedule and task trace (all 28 days)

### Week 1

| Date | Priority | Epic / Story | Task ID — implementation work | Hours | Tests | Dependency |
|---|---|---|---|---:|---|---|
| 2026-10-19 Mon | P0 | E0-01 / S0-01 | **P00** — Initialize Windows-native FastAPI project, venv, repo structure | 3 | T-01 | None |
| 2026-10-19 Mon | P0 | E0-01 / S0-01 | **P01** — Import/check immutable Demo Salon fixtures, schema and pinned clock | 3 | T-01 | P00 |
| 2026-10-20 Tue | P0 | E0-02 / S0-02 | **P02** — Define four ChannelAdapter contracts + normalized request, P2 telephony stub | 3 | T-10 | P00 |
| 2026-10-20 Tue | P0 | E0-02 / S0-02 | **P03** — Spike actual mic/STT/TTS in named browser and log compatibility | 3 | T-10 | P02 |
| 2026-10-21 Wed | P0 | E0-01 / S0-03 | **P04** — Implement SQLite session/message/audit creation and lifecycle | 3 | T-01 T-08 | P01 |
| 2026-10-21 Wed | P0 | E0-01 / S0-03 | **P05** — Create FastAPI start/end/message endpoints with Pydantic schemas | 3 | T-01 T-08 | P04 |
| 2026-10-22 Thu | P0 | E0-04 / S0-04 | **P06** — Implement deterministic OKF approved index/source matching | 3 | T-02 T-03 | P01 P05 |
| 2026-10-22 Thu | P0 | E0-04 / S0-04 | **P07** — Add hours/FAQ response composer with source IDs and abstention | 3 | T-02 T-03 | P06 |
| 2026-10-23 Fri | P0 | E0-05 / S0-05 | **P08** — Build read-only synthetic haircut availability tool and date parsing | 3 | T-04 T-05 | P04 P05 |
| 2026-10-23 Fri | P0 | E0-05 / S0-05 | **P09** — Preserve Friday→Saturday multi-turn correction and no-write tests | 3 | T-04 T-05 | P08 |
| 2026-10-24 Sat | P0 | E0-03 / S0-06 | **P10** — Verify eligible free hosted Groq model/quotas and implement LLM classifier | 3 | T-12 | P05 |
| 2026-10-24 Sat | P0 | E0-03 / S0-06 | **P11** — Add rules fast path, Pydantic intent validation, timeout/429 fallback | 3 | T-12 | P10 |
| 2026-10-25 Sun | P0 | E0-07 / S0-07 | **P12** — Build simple browser text UI integrated with normalized channel | 3 | T-09 T-11 | P07 P09 P11 |
| 2026-10-25 Sun | P0 | E0-07 / S0-07 | **P13** — Integrate LangGraph intent→capability→tool branches; core tests | 3 | T-09 T-11 | P12 |

### Week 2

| Date | Priority | Epic / Story | Task ID — implementation work | Hours | Tests | Dependency |
|---|---|---|---|---:|---|---|
| 2026-10-26 Mon | P0 | E0-02 / S0-08 | **P14** — Complete live mic→STT→backend response→audible TTS loop | 3 | T-10 T-11 | P03 P12 |
| 2026-10-26 Mon | P0 | E0-02 / S0-08 | **P15** — Implement mic denial/noisy speech handling, typed fallback, metadata | 3 | T-10 T-11 | P14 |
| 2026-10-27 Tue | P0 | E0-02 / S0-09 | **P16** — Build simulated-call start/end controls and continuous session state | 3 | T-01 T-08 T-10 | P14 |
| 2026-10-27 Tue | P0 | E0-02 / S0-09 | **P17** — Persist voice transcript/outcome, speaker disclosure and channel audits | 3 | T-01 T-08 T-10 | P16 |
| 2026-10-28 Wed | P0 | E0-06 / S0-10 | **P18** — Implement customer-confirmed queued handoff ticket write and true ID | 3 | T-19 | P04 P05 |
| 2026-10-28 Wed | P0 | E0-06 / S0-10 | **P19** — Protect staff read/list API with server secret; deny/allow tests | 3 | T-20 | P18 |
| 2026-10-29 Thu | P0 | E0-07 / S0-11 | **P20** — Run complete P0 three-intent voice/sim-call/text end-to-end suite | 3 | T-01..T-12 T-19 T-20 | P13 P17 P19 |
| 2026-10-29 Thu | P0 | E0-07 / S0-11 | **P21** — Fix blockers; capture working LLM result, STT/TTS clip and staff queue evidence | 3 | T-01..T-12 T-19 T-20 | P20 |
| 2026-10-30 Fri | P1 | E1-01 / S1-01 | **A00** — Design approved corpus chunking and vector retrieval adapter schema | 3 | T-P1-01 | P06 P21 |
| 2026-10-30 Fri | P1 | E1-01 / S1-01 | **A01** — Implement lightweight semantic index under laptop/budget constraints | 3 | T-P1-01 | A00 |
| 2026-10-31 Sat | P1 | E1-01 / S1-02 | **A02** — Build combined OKF+RAG evidence fusion/de-duplication | 3 | T-P1-01 | A00 A01 |
| 2026-10-31 Sat | P1 | E1-01 / S1-02 | **A03** — Test RAG-empty fallback, conflicts, paraphrase recall and approval | 3 | T-P1-01 | A02 |
| 2026-11-01 Sun | P1 | E1-01 / S1-02 | **A04** — Wire RAG flag and source-grounded result view/metrics | 3 | T-P1-01 | A02 A03 |
| 2026-11-01 Sun | P1 | E1-01 / S1-02 | **A05** — Stabilize semantic provider fallback and commit P1 knowledge demo | 3 | T-P1-01 | A04 |

### Week 3

| Date | Priority | Epic / Story | Task ID — implementation work | Hours | Tests | Dependency |
|---|---|---|---|---:|---|---|
| 2026-11-02 Mon | P1 | E1-02 / S1-03 | **A06** — Implement Urdu language-aware session, STT and ASR adapter choice | 3 | T-P1-02 | P14 P21 |
| 2026-11-02 Mon | P1 | E1-02 / S1-03 | **A07** — Build Urdu→English translation normalization preserving dates/IDs | 3 | T-P1-02 | A06 |
| 2026-11-03 Tue | P1 | E1-02 / S1-04 | **A08** — Implement English→Urdu response translation + Urdu-capable TTS | 3 | T-P1-02 | A06 A07 |
| 2026-11-03 Tue | P1 | E1-02 / S1-04 | **A09** — Test actual Urdu audio, 429/voice fallback and translated identifiers | 3 | T-P1-02 | A08 |
| 2026-11-04 Wed | P1 | E1-03 / S1-05 | **A10** — Implement complexity assessment and specialized agent registry | 3 | T-P1-03 | P13 P21 |
| 2026-11-04 Wed | P1 | E1-03 / S1-05 | **A11** — Build FAQ/booking/support agents using existing domain tools; compare simple path | 3 | T-P1-03 | A10 |
| 2026-11-05 Thu | P1 | E1-04 / S1-06 | **A12** — Build local MCP server wrapping approved direct tools and typed schemas | 3 | T-P1-04 | P13 P21 |
| 2026-11-05 Thu | P1 | E1-04 / S1-06 | **A13** — Build MCP client/provider adapter with scoped ACL, timeout and audit tests | 3 | T-P1-04 | A12 |
| 2026-11-06 Fri | P1 | E1-05 / S1-07 | **A14** — Add optional P1 SQLite booking migration and synthetic authentication context | 3 | T-P1-05 | P08 P19 |
| 2026-11-06 Fri | P1 | E1-05 / S1-07 | **A15** — Implement guarded create/reschedule/cancel with atomic idempotency & tests | 3 | T-P1-05 | A14 |
| 2026-11-07 Sat | P1 | E1-06 / S1-08 | **A16** — Implement synthetic CRM lookup and audited ticket status changes | 3 | T-P1-06 | P18 A13 |
| 2026-11-07 Sat | P1 | E1-06 / S1-08 | **A17** — Add analytics/accessibility/UI improvement and extended FAQ, demo evidence | 3 | T-P1-06 | A16 |
| 2026-11-08 Sun | P1 | E1-06 / S1-09 | **A18** — Run P1 cross-feature end-to-end tests, including Urdu RAG/MCP agent paths | 3 | T-P1-01..06 | A05 A09 A11 A13 A15 A17 |
| 2026-11-08 Sun | P1 | E1-06 / S1-09 | **A19** — Fix high-priority integration defects and package P1 evidence/limitations | 3 | T-P1-01..06 | A18 |

### Week 4

| Date | Priority | Epic / Story | Task ID — implementation work | Hours | Tests | Dependency |
|---|---|---|---|---:|---|---|
| 2026-11-09 Mon | QA | EF-01 / SF-01 | **F00** — Run full P0/P1 regression, external-free-model quota/429 and voice/browser matrix | 6 | T-01..T-P1-06 | P21 A19 |
| 2026-11-10 Tue | QA | EF-01 / SF-02 | **F01** — Security/privacy audit: staff endpoint, P1 writes, MCP scopes, injection, retention | 6 | T-07 T-P1-04 T-P1-05 | F00 |
| 2026-11-11 Wed | QA | EF-01 / SF-03 | **F02** — Fix top-severity defects, collect performance and accuracy measurements | 6 | T-10 T-12 T-P1-01 | F01 |
| 2026-11-12 Thu | QA | EF-02 / SF-04 | **F03** — Rehearse end-to-end demo; generate separate November synthetic slots if needed | 6 | T-04 T-10 | F02 |
| 2026-11-13 Fri | QA | EF-02 / SF-05 | **F04** — Freeze P1 feature scope, complete README/manual, architecture evidence and setup | 6 | T-01..T-P1-06 | F03 |
| 2026-11-14 Sat | QA | EF-02 / SF-06 | **F05** — Produce final screenshots, test matrix, report, slide/recorded demo | 6 | T-01..T-P1-06 | F04 |
| 2026-11-15 Sun | QA | EF-02 / SF-07 | **F06** — Final reproducibility review, project audit and submission handoff | 6 | T-01..T-P1-06 | F05 |

## Dependency rules and implementation gates

P0 language/provider and tool interfaces are light scaffolding only; the working direct tools and browser voice/LLM matter more than architectural ornament. P1 RAG uses P0 approved knowledge, specialized agents invoke existing safe tools, local MCP exposes existing authorized service contracts, and booking operations remain OFF until confirmation/idempotency tests pass. Urdu requires actual ASR and TTS tests with synthetic utterances. Without a passing hosted LLM or spoken voice test, mark the relevant P0 gate BLOCKED even when text-only fallback works.

## Slip response / backlog governance

If P0 is incomplete on Oct 29, reassign **A00–A05** (Oct 30–Nov 1) to P0 recovery and move those RAG tasks to the first available P1 days. Recompute available hours at the Nov 1 review; prioritize RAG+Urdu+MCP+agents first, then P1 booking/CRM/UI by risk and remaining time. P1 may continue to Nov 11–12, but Nov 13–15 are always protected for release evidence. Mark deferred P1 task IDs explicitly as `Deferred (schedule contingency)`; do not delete them or change their priority.

## Weekly progress math

Track per tier: planned task hours, completed task hours, actual elapsed hours, passed tests/total tests, unresolved blockers, screenshots/demo links, code commits. **P0 burn-up and P1 burn-up are separate.** At every Sunday review record WIP vs PASS vs BLOCKED and show a 3–5-minute running increment.
