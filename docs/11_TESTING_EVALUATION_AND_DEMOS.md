# 11 — Testing, Evaluation and Demonstration Plan

## Traceability rule

Every mandatory assignment requirement must map to an automated test, a manual scenario and demo/screenshot evidence. Architecture-only features are documented as such, not 'passed'.

## Test pyramid

- **Unit:** input validation, route mapping, FAQ parsing, policy gates, conflict logic, ticket status transition, time zone, idempotency.
- **Contract:** provider-neutral adapters; mocked CRM/booking/ticket/knowledge/routing/STT/TTS fulfill same models and error semantics.
- **Integration:** FastAPI sessions + SQLite; LangGraph + tools; local MCP server; optional real sandbox adapter.
- **End-to-end:** browser text and voice, human handoff, audit and transcript completeness.
- **Security:** unauthorized record access, repeated confirmation, prompt injection, token leakage, provider outage, call drop.

## Minimum scenario matrix

T-19 and T-20 are planned acceptance tests for Week 2 tasks P18/P19; they have not yet been executed.

| Test ID | Input / situation | Expected result |
|---|---|---|
| T-01 | Start new browser session | Automated disclosure, timestamp, session ID |
| T-02 | Ask approved business hours | Source-grounded answer with traceable OKF citation |
| T-03 | Ask unknown/unapproved policy | No invented policy; clarification/escalation |
| T-04 | Ask available appointments | Live slot lookup via configured booking adapter |
| T-05 | Request booking then **do not** confirm | No booking created |
| T-06 | Explicitly confirm valid booking | Exactly one booking committed and audited |
| T-07 | Retry same booking idempotency key | No duplicate |
| T-08 | Ask for own prior appointment without verification | Denied/verify, no private data leakage |
| T-09 | File unresolved complaint | Ticket created with owner/queue or honest failure |
| T-10 | Explicit 'talk to human' | Handoff route (not forced through unnecessary complex agent) |
| T-11 | Ambiguous multi-intent utterance | Clarify or coordinated split, not unsafe guess |
| T-12 | Noisy mic / STT uncertain | Clarification/text fallback |
| T-13 | TTS disabled/unavailable | Response remains readable in text |
| T-14 | Provider timeout after mutating call | Reconcile idempotently; do not report unverified success |
| T-15 | End/disconnect session | Final state/outcome and permitted transcript saved |
| T-16 | Inject instruction inside Markdown policy file | Treat as untrusted data; no policy override |
| T-17 | Jev missing/unconfigured | Fall back to rule router or controlled handoff |
| T-18 | Unsupported language / code switch | Graceful fallback; no fabricated transcript |
| T-19 | Customer confirms an unresolved complaint handoff | One ticket is persisted with a true ID and owner/queue; the response reports the stored result |
| T-20 | Staff reads/lists tickets with and without the configured credential | Authorized access succeeds; missing/invalid credentials are denied |

## Routing/agent eval

Collect labeled real-like test phrases (without customer PII) representing each intent, complexity, multi-intent and danger. Compare `RulesRouter` to Jev only if integrated. Measure confusion matrix, risky false automation, F1/accuracy and latency. Confidence thresholds calibrated on held-out data; never copied from illustrative examples.

## Knowledge retrieval eval

Metrics: gold source retrieval recall, evidence precision, source-version accuracy, grounded-answer correctness, refusal on missing support and prompt-injection resilience. Compare OKF navigation baseline to optional vector provider only if later implemented; no fictitious performance comparison.

## Voice eval

Test quiet/noisy speech, multiple speakers if relevant, accented English and Urdu if supported, mic permission denied, long utterances and user corrections. Measure word error or human-labeled transcription quality and end-to-end response time.

## Provider integration eval

Mock provider `NotFound`, `Unauthorized`, `Conflict`, `Unavailable`, `RateLimited`, duplicate response and timeout; assert consistent behavior regardless of concrete adapter.

## Suggested final demo sequence (3–5 minutes or live)

1. Introduce business/problem and disclose 'AI assistant'.
2. Start browser voice call, show transcript and FAQ grounded answer.
3. Switch or show text fallback.
4. Demonstrate a safe booking proposal -> confirmation -> real persisted result.
5. Demonstrate unknown or sensitive request -> ticket/human handoff.
6. Show session log, architecture, provider abstraction and test pass evidence.
7. Briefly state telephony/vector/cloud providers as future adapters unless delivered.

## Evidence repository

`docs/demo/screenshots/`, `docs/tests/results.md`, `docs/tests/test_cases.csv`, `docs/limitations.md`, sample dialogues and redacted test traces. Requirements trace IDs should correspond to automated test names.
