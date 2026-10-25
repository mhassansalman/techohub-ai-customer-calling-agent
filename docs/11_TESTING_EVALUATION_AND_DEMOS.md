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
T-21 is the browser voice-chat acceptance test for P14.

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
| T-21 | Speak a question in the React chat, then send a typed question in the same session | Final speech transcript uses the existing backend session; the actual returned assistant answer appears and is spoken; typed follow-up continues in that session |

## P03 and P10 Week 1 verification record — 2026-10-25

### P03 — browser voice compatibility

- **Browser/runtime:** VS Code integrated browser; user agent reported Chromium Chrome 150.0.7871.250, Electron 43.7.7, and Code/1.143.1. Page ran in a secure context over `http://127.0.0.1`.
- **Microphone:** permission check passed; a `getUserMedia` test stream was stopped without recording.
- **Speech recognition:** `SpeechRecognition` API was available and the test was started. The browser returned `network` before any transcript was received.
- **Speech synthesis:** API was available; the test utterance reached the synthesis `onend` event. No human confirmation of audible output was available.
- **Result:** **Partial.** Browser APIs and microphone permission were verified, but recognition failed in this environment and audible TTS was not confirmed. This is only the P03 compatibility spike, not an integrated voice conversation.

### P10 — hosted Groq classifier

- Existing configuration resolved the API key as present without printing it and selected `openai/gpt-oss-20b`; configured bounds were a 5-second attempt timeout, at most one retry, and an 8-second total deadline.
- One safe request was sent: “Could you tell me whether pets are allowed in the salon?” The existing Groq adapter returned a successfully parsed result: `faq_service_policy`, confidence `0.90`, with no service/date entities. This verifies provider/model access for that request at that time, not classification correctness for the question.
- Existing automated tests cover the intent allowlist and Pydantic validation, invalid structured output, timeout sanitization, bounded 429 retry, and rules/clarification fallback (`tests/test_intent.py`).
- The single successful request does not establish whether the account is on an eligible free tier or reveal its quota limits. No account dashboard or quota evidence was available during this check.
- **Result:** **Partial.** A live hosted classification succeeded, but the Week 1 free-account eligibility/quota prerequisite remains unverified.

## P14 browser voice-chat integration verification — 2026-10-25

- **Implementation:** The React chat now requests microphone access, starts browser speech recognition, submits a non-empty final transcript through the existing message API, and speaks only the actual assistant response returned by that successful request. Typed turns continue to use the same session and stay text-only. Recognition cancellation, duplicate final events, browser API absence, permission failures, and speech playback failures have focused frontend coverage.
- **Automated results:** All 24 frontend tests passed, including mocked Web Speech API checks for same-session submission and assistant-response TTS. The frontend production build passed. These mocks do not establish live microphone recognition or audible playback.
- **Browser/runtime:** VS Code integrated browser, Chromium Chrome 150.0.7871.250 / Electron 43.7.7; `http://127.0.0.1:5173` was a secure context. Both `SpeechRecognition` and `speechSynthesis` APIs were present.
- **Microphone and recognition:** Clicking the React microphone requested access and advanced to the listening state, confirming the browser permission request completed. Speech recognition then reported a `network` error before producing a transcript. No voice-originated request reached the backend and no voice response was spoken.
- **Typed same-session check:** After recognition failed, a typed “Are you open on Wednesday?” turn in that same browser session reached the real FastAPI/LangGraph workflow and displayed “Demo Salon is open on Wednesday, 09:00–18:00 Etc/UTC.” Typed responses intentionally do not trigger TTS.
- **Additional Chrome acceptance (user-observed):** The user manually verified the complete flow in regular Google Chrome: “Are you open on Sunday?” was recognized and appeared in the React conversation; the existing backend returned “Demo Salon is closed on Sunday.”; that response appeared in chat and was audibly spoken by browser TTS; the interface displayed “Voice reply finished.” The Chrome version was not provided. This is user-reported acceptance evidence, distinct from the earlier VS Code integrated-browser failure above.
- **Result:** **Complete; T-21 passed.** The user-observed Chrome run verifies final speech transcription, transcript display, actual backend response, and audible speech of that response. The frontend test suite verifies voice and typed turns share the existing session and endpoint. The earlier P03 compatibility result remains unchanged and is not retroactively upgraded.

### Routing and availability follow-up — 2026-10-25

These user-observed responses were potential intent-routing/capability issues, not failures of the P14 voice transport integration:

- “Are you open on Sunday? How much is one haircut?” produced a clarification response rather than handling both intents.
- “Which slots are open on Wednesday?” produced “I can't confirm appointment slots from the service catalog.”
- **Root cause verified:** The rules classifier returned only `faq_business_hours` for both messages. The first mixed hours and service topics in one knowledge query; the second treated “slots open” as an hours FAQ. The Groq fallback was bypassed for these single-intent rule results.
- **Correction verified:** Compound hours-plus-service questions now route through the existing multi-intent capability with separate grounded FAQ queries. Slot wording routes to availability; a missing service is clarified, and the requested date is retained for a follow-up service answer. The immutable fixture has no haircut slots for the next Wednesday, 2026-11-04, and the response reports no recorded slots rather than inventing availability.
- **Regression coverage:** Backend tests cover both compound question orders, existing hours-plus-availability behavior, deterministic single-intent routing, missing-service date preservation, no-recorded-slot behavior, Groq call bounds, and the unchanged voice/text response contract.

### Full-pipeline stabilization — service matching and availability follow-ups

- **Confirmed defects:** The classifier, knowledge retrieval, and availability lookup used separate service-phrase matchers. As a result, “beard trimming” could classify as a service but fail grounded FAQ retrieval, and “haircut and beard combo” was not consistently recognized. Availability follow-ups such as “What about Saturday instead?” could also misclassify conversational filler (“about”) as an unknown service.
- **Correction:** Service aliases, phrase normalization, and overlap resolution now share one fixture-backed resolver across classification, grounded knowledge retrieval, and availability. Availability context handling treats the tested date-correction wording as a follow-up, not an unknown service. Fixture data, API contracts, and backend routing architecture are unchanged.
- **Acceptance replay:** 18 unique utterances were sent through FastAPI and the compiled LangGraph workflow using the deterministic classifier, including same-session service/date follow-ups. All requests returned successfully and produced grounded catalog/hours/fixture answers or safe clarification/unsupported responses. No slots were inferred beyond the immutable fixture.
- **Provider smoke check:** One sanitized live Groq request for “Is beard trimming offered at your salon?” returned a validated `faq_service_policy` classification grounded to `beard-trim`. This confirms that single request and the updated entity grounding path, not general model correctness.
- **Automated verification:** 193 backend tests and 24 frontend tests passed; the frontend production build passed. The canonical salon fixture and Week 1 backlog were unchanged.

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
