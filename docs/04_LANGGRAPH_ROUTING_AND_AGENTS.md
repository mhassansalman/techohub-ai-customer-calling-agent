# 04 — LangGraph Routing, Jev and Agent Strategy

## Decision: hybrid intelligence

- **Simple/known request:** controlled deterministic workflow using native or MCP-exposed tools; never require autonomous agent loops for routine DB lookups.
- **Complex multi-step request:** a specialized reasoning agent (or subgraph) receives only the tools, context and authority necessary for its task.
- **Sensitive/unsupported/unverified request:** human handoff/clarification or guarded workflow; intent complexity alone is insufficient to determine safety.
- **Multi-intent:** split into supported sub-requests or clarify; preserve shared state.

## Jev: important correction to earlier discussion

**TypeSafe Jev is a decision model, not just a JSON routing schema.** It makes typed semantic judgments that code can act on, such as bounded `Choice` for intent, `Score` for complexity or risk, and a yes/no-type signal. It does not generate normal conversational answers. The official TypeSafe intent-routing example classifies intent/complexity before dispatch to deterministic handlers, specialist LLMs or humans: https://docs.typesafe.ai/patterns/intent-routing . LangChain also describes a concrete Jev + LangGraph pairing: https://www.langchain.com/blog/building-prod-with-jev-and-langgraph .

**Status:** strong candidate, **not yet proven available, free or integrated**. Keep a `RouterProvider`/`IntentRouter` port and compare:

1. `RulesRouterAdapter` — free transparent baseline; direct human requests, known commands and guardrails.
2. `JevRouterAdapter` — optional when access and cost permit; classify `intent`, `complexity`, `needs_human`/`risk`, preserve probabilistic signal.
3. `LLMRouterAdapter` — optional fallback using local/cloud structured output with schema validation.

**Do not** call a confidence number `0.96` without measured calibration. Define route confidence thresholds after evaluation data, not in speculative code.

## Proposed canonical RoutingDecision

```json
{
  "intent": "appointment_reschedule",
  "complexity": "simple",
  "risk_level": "medium",
  "route": "booking_workflow",
  "confidence": null,
  "requires_identity_verification": true,
  "requires_confirmation": true,
  "reason_code": "known_booking_change"
}
```

`confidence` is nullable because rule-based routers may not provide meaningful calibrated scores. `risk_level` is independently validated against deterministic business rules.

## Intent taxonomy (initial *proposal*, adapt to selected business)

| Intent | Execution | Dependencies |
|---|---|---|
| `faq_business_hours` | Simple knowledge workflow | OKF knowledge |
| `faq_service_policy` | Simple evidence workflow; multi-part could use knowledge agent | OKF knowledge |
| `appointment_availability` | Simple booking workflow | Booking provider |
| `appointment_create` | Stateful workflow; confirm before commit | Booking provider, optional CRM |
| `appointment_modify` | Stateful protected workflow | Identity, booking provider |
| `customer_account_lookup` | Verified data retrieval | CRM provider |
| `complaint` | Simple intake -> ticket; complex resolution -> specialist | CRM, tickets, knowledge |
| `human_request` | Direct handoff | Ticket/queue |
| `unsupported` | Clarify or handoff | Router + escalation policy |

These intents are not all required by the assignment; **minimum three** must work completely.

## Proposed minimal LangGraph state

```python
class ConversationState(TypedDict, total=False):
    session_id: str
    channel: str
    messages: list
    latest_user_text: str
    customer_id: str | None
    auth_status: str
    consent_status: str
    route: dict
    evidence: list
    action_proposal: dict | None
    awaiting_confirmation: bool
    action_result: dict | None
    escalation: dict | None
    response_text: str
    status: str
```

### Graph outline

`START -> guard/disclose -> classify -> route_decision -> [simple_workflow | specialist_subgraph | clarify | escalation] -> validate/evidence/confirmation -> log -> END`.

External channel delivery / optional TTS happens **after** text response is returned from the graph. Subgraphs may loop to ask a missing detail; the next user turn re-enters with the persisted checkpoint.

## Proposed specialized agents (only activate if evaluation shows value)

- **Knowledge Research Agent:** synthesizes multiple policy/service documents and preserves citations. Basic FAQ lookup is a tool, not an agent.
- **Customer Resolution Agent:** combines complex complaint context, verified CRM history and published policies; may open a ticket but cannot promise refund approval.
- **Scheduling Negotiation Agent:** explores multi-person, multi-location or multi-constraint options; final book action remains a guarded deterministic service.

Avoid three always-running agents. The simplest effective graph may start with only one complex-case agent. Agent inventory is **provisional**.

## Guard sequence for consequential actions

1. Check authorization (a name or telephone number alone is not proof).
2. Retrieve live state, e.g. appointment and slot.
3. Explain exact proposed action: service/date/time/location/customer.
4. Wait for explicit confirmation from user.
5. Enforce transactional check and idempotency key in domain service.
6. Execute through provider adapter; only claim success on authoritative provider response.
7. Audit trace + final response; if interrupted resume without duplicate action.

## Route evaluation

Build labeled corpus (e.g. 15+ examples per mandatory intent plus ambiguous, multi-intent, policy-sensitive, speech errors). Measure intent accuracy, inappropriate automation rate, complexity classification, false confidence, handoff precision, and p50/p95 routing latency. Compare baseline rules vs Jev vs structured LLM **if** integrated. Never assume Jev is faster on local workload solely from vendor benchmarks.
