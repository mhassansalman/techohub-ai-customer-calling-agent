# 02 — SRS: Functional and Nonfunctional Requirements

> Requirements labeled **M** originate in or directly support the mandatory assignment; **E** are agreed/planned enhancements; **F** are future/optional. IDs are stable for backlog and test mapping.

## Actors & scope

**Customer, Human Support, Business Admin, System/Provider.** Exact sample-business scenario TBD. Data shown to customers must be mock or verified owned data; knowledge policies must be approved by an admin.

## Functional requirements

| ID | Priority | Requirement | Acceptance / evidence |
|---|---|---|---|
| FR-01 | M | Start a session and provide automated-assistant disclosure | Transcript begins with a clear automation disclosure; session ID/time recorded |
| FR-02 | M | End or time out a session safely | End timestamp/outcome persisted; disconnection handled |
| FR-03 | M | Text chat and text fallback | User can complete core scenario by text if mic unavailable |
| FR-04 | M | Speech input (STT) | Microphone audio yields transcript and a user-visible recognition-failure fallback |
| FR-05 | M | Speech output (TTS) | Approved text response can be spoken; user can mute/read text |
| FR-06 | M | Recognize >= 3 defined intents | Per-intent happy paths tested; unsupported routed safely |
| FR-07 | M | Approved FAQ knowledge retrieval | Responses derive from approved document excerpts; missing information handled as unknown |
| FR-08 | M | Maintain multi-turn session context | 'Actually Saturday' attaches to pending appointment request, not a new unknown request |
| FR-09 | M | Persist date/time, intent, conversation/transcript or permitted summary, outcome | Viewable staff log with retention policy and access controls |
| FR-10 | M | Human escalation | On uncertainty, sensitive requests, explicit customer request; ticket/queue or clear handoff state |
| FR-11 | M | Avoid unauthorized commitments | Agent does not promise refunds, approvals or appointments without successful confirmed tool result |
| FR-12 | M | Test noisy/unclear speech | Low transcription quality triggers repetition/text fallback, not fabricated actions |
| FR-13 | E | Search customer record/history | Verified authorized customer data only via `CRMProvider` |
| FR-14 | E | Check availability, create, reschedule, cancel bookings | Conflicts checked; mutations require confirmation and idempotency |
| FR-15 | E | Create/update/follow-up ticket | Ticket ID, status, owner/queue, links to session/customer as appropriate |
| FR-16 | E | Route simple/complex/sensitive requests | Approved, deterministic route mapping; uncertainty gate; specialist only when justified |
| FR-17 | E | Swappable knowledge retrieval | OKF baseline; provider interface returns canonical evidence records |
| FR-18 | E | Swappable local/external business providers | Adapter contract tests; no provider-specific types in domain core |
| FR-19 | E | Expose reusable capability tools through MCP | Explicitly scoped tools; authorization enforced server-side |
| FR-20 | E | Analytics dashboard / audit | Basic counts, resolution, escalation, latency, failures (no unsubstantiated sentiment claims) |
| FR-21 | F | Real phone call via Twilio/SIP | Optional validated phone session with callbacks and audio handling |
| FR-22 | F | SIM/GSM gateway | Experimental only, dependent on tested audio access/hardware |
| FR-23 | F | External CRM/booking/helpdesk implementation | Only claim after credentials, API contract and end-to-end tests |
| FR-24 | F | Vector knowledge retrieval | ChromaDB/FAISS/Milvus adapters planned, absent from baseline |

## Nonfunctional requirements

| ID | Requirement | Objective / how tested |
|---|---|---|
| NFR-01 | Maintainable modularity | Static import check: domain core not dependent on Twilio/MCP/FastAPI/Chroma providers |
| NFR-02 | Reliability | On unavailable integration: timeout, bounded retry on safe reads, explicit fallback/escalation |
| NFR-03 | Security | Authentication, per-customer authorization, protected secrets, no raw provider keys in transcript |
| NFR-04 | Privacy | Consent before recording, retention policy, avoid storing raw audio by default |
| NFR-05 | Transaction safety | No duplicate bookings/tickets from retries; mutation approvals required; audit records |
| NFR-06 | Observability | Correlation IDs across channel, router, agent, adapter, and session log |
| NFR-07 | Usability | Text fallback, readable transcript and accessible explicit handoff option |
| NFR-08 | Latency | Track end-to-end and segment latencies; set realistic thresholds only after local benchmarks |
| NFR-09 | Portability | Run baseline locally without Docker or paid APIs |
| NFR-10 | Testability | Mock each provider, run unit + contract + integration + end-to-end scenario tests |
| NFR-11 | Grounding | Quote source IDs / policy version in internal evidence; no fabricated KB policy |
| NFR-12 | Voice compatibility | Canonical audio formats/metadata, disconnects and partial transcript support |

## System context / input-output contract

**Input:** normalized `CustomerMessage(text, session_id, channel, timestamp, language?, speech_confidence?, customer_identity_context?)`.  
**Output:** `AgentResponse(text, status, citations[], action_results[], requires_followup, handoff_info?, speech_hint?)`.

## Main use cases

- **UC-01:** Hours/policy FAQ -> knowledge retrieve -> approved answer or unknown.
- **UC-02:** Appointment availability -> check booking adapter -> quote verified slots -> confirm before create.
- **UC-03:** Existing booking -> authenticate customer -> retrieve records -> authorized disclosure.
- **UC-04:** Complex complaint/refund -> gather context, retrieve rules and customer record, create ticket if appropriate -> human review, no automatic refund promise.
- **UC-05:** Explicit 'human please' -> direct escalation without unnecessary model decision.
- **UC-06:** Voice input fails -> apologize briefly, repeat or text fallback.

## Constraints and exception rules

- FAQ is **not** an authority for live appointment inventory or personal customer state; query the appropriate provider.
- Router confidence is evidence for handling ambiguity, **not** authorization to execute a high-impact action.
- A ticket records follow-up; it does not imply the issue was resolved.
- Channel adapter manages socket/call lifecycle before STT; core receives text after STT.
- External provider availability/terms must be checked before selecting it for the timeline.

## TBD before requirements sign-off

Business scenario, initial 3+ intent taxonomy, approved KB content, booking schema details, customer identity proof, team workload, latency targets, provider selection and privacy retention schedule.
