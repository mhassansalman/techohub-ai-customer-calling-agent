# 09 — Security, Privacy, Guardrails and Reliability

## Threat model overview

Protected assets: customer PII, session transcripts, appointment records, credentials, knowledge-policy integrity, staff/admin actions, audio recording and external provider operations. Threats: impersonation, prompt injection, unauthorized transactions, cross-tenant disclosure, duplicate writes, stolen API keys, poisoned knowledge and telephony spoofing.

## Identity verification

- **General FAQ:** no identity needed; user remains anonymous.
- **Private profile/booking lookup:** obtain sufficient approved verification (e.g. demonstration OTP/mock verification), then authorization context maps the session to the customer. A phone number or caller ID alone is not proof.
- **Mutation of private records:** verification **and** confirmation, not one or the other.
- **Human handoff:** can be requested anonymously; avoid exposing private history to unauthorized staff.

## Layered action gate

`Propose -> validate policy -> authenticate/authorize -> retrieve fresh state -> present exact change -> receive explicit confirmation -> execute idempotently -> persist result -> tell customer verified outcome.`

Guard rails outside model: input schemas, permission checks, explicit approval state, DB constraints, rate limits, audit events. Jev's risk score or agent output may assist routing, but must **never override deterministic guardrails**.

## Knowledge/RAG protection

- Whitelist approved OKF docs and verify frontmatter/index; unsafe documents must not act as instructions.
- Differentiate business source content from system policy and customer chat messages.
- Check document version, validity and tenant scope.
- No source found -> explain uncertainty, don't invent policy.
- Minimize quoted sensitive records in user-facing transcript.

## Tool/MCP security

- The MCP tool schema advertises only approved operations, **not** arbitrary SQL, file system or remote execution.
- Identity derived from trusted server session; model-supplied IDs are untrusted references, not authorization.
- Service enforces RBAC/ABAC and per-resource checks; MFA/OAuth where third-party integration requires it.
- Store credentials in env/secret storage and redact from tool traces.
- Cap tool execution time, request volume and return sizes.

## Call and speech privacy

- Agent identifies itself as AI at start.
- Record call/audio only with appropriate consent; separate permissible transient processing vs retained recordings.
- Store text transcripts or redacted summaries according to assignment and retention policy.
- Do not claim all phone providers/regions permit call recording or telephony gateways.
- Provide access control and deletion/retention procedure for demo records.

## Reliability strategy

| Failure | Expected safe behavior |
|---|---|
| STT fails | Ask to repeat or switch to typed input |
| Jev unavailable | Use validated rules/LLM route fallback, preserve route reason |
| Knowledge retrieval empty | Admit missing answer and offer escalation |
| CRM unavailable | Do not fake customer status; log and handoff |
| Booking provider times out after submission | Query/reconcile by idempotency key before reissuing mutation |
| Ticket provider unavailable | Queue local handoff if allowed; tell customer honest status |
| Call dropped | Persist pending work and session outcome; never silently complete unconfirmed action |
| Human unavailable | Create clearly labeled queued ticket or provide contact path, if supported |
| Low-confidence routing | Clarify or escalate, rather than choosing arbitrary high-impact path |

## System logging and observability

- Correlation `trace_id` spans inbound event -> STT -> router -> workflow -> provider -> response/TTS.
- Record `router_provider`, proposed/selected intent, outcome, exception code, latency, provider used, handoff and audit result.
- Store meaningful safe excerpts or hashed identifiers; don't leak keys or raw PII into diagnostics.
- Suggested metric categories: intent errors, unsupported rate, hallucination/ungrounded answers, STT corrections, booking conflicts, handoffs, p50/p95 latency, tool failures.

## Security test catalog

Unauthorized profile retrieval; fake caller ID; malicious Markdown instructions; prompt asks to ignore policy; booking retry; repeated 'yes' from stale session; expired confirmation; slot race; third-party token expiry; transcript accidentally containing secrets; redirected MCP tool; disconnect mid-action.
