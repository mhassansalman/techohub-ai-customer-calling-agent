# 05 — CRM, Booking, Tickets, Native Tools and MCP

## Why three business capabilities?

| Capability | Answers | Owns | Does NOT inherently own |
|---|---|---|---|
| CRM | Who is the customer and what is their history? | Profile, interaction history, verified customer context | Live availability, refund approval |
| Booking | What slots exist and what appointment is committed? | Services, calendars, slots, appointments, conflict detection | Full complaints lifecycle |
| Ticket / case | Which unresolved issue needs follow-up, by whom, by when? | Status, priority, owner/queue, resolution notes, escalation | Customer master profile, schedule inventory |

**Concrete example:** Customer asks for a refund after cancellation. CRM retrieves verified customer context; booking supplies appointment/cancellation facts; OKF supplies approved cancellation/refund policy; ticket records unresolved refund request and human owner. A ticket is not a refund payment, and creating one does not authorize refund.

A real CRM can contain built-in tickets. **Logical capability interface != separate product, database or microservice.** Initial local CRM/booking/tickets may share SQLite tables.

## Provider ports, implementations and scope

| Port | Baseline adapter (planned) | Future adapter examples | Status |
|---|---|---|---|
| `CRMProvider` | `LocalCRMAdapter` / SQLite | HubSpot, Zoho, Salesforce | Port and local implementation targeted; external not committed |
| `BookingProvider` | `LocalBookingAdapter` / SQLite | Google Calendar, Cal.com | Port and local implementation targeted; external one-off demo TBD |
| `TicketProvider` | `LocalTicketAdapter` / SQLite | Zendesk, Freshdesk, CRM ticketing | Port and local implementation targeted; external not committed |

Standardize models and error types: `NotFound`, `Unauthorized`, `Conflict`, `RateLimited`, `Unavailable`, `ValidationError`; avoid exposing provider-specific objects to LangGraph.

## Native tools vs MCP

**Native tools:** `search_knowledge`, `validate_inputs`, `summarize`, `detect_language`, `prepare_action_proposal`, and direct service functions when internal. A deterministic system must invoke audit/security without waiting for model tool selection.

**MCP:** Provide scoped, reusable model-callable interfaces to CRM, booking and ticket operations. Useful if multiple AI clients or independently deployed services consume them. Suggested logical MCP servers: CRM, Booking, Tickets. For a modest implementation, one consolidated `business_mcp_server` exposing clearly named tools is also valid and potentially simpler.

Example MCP tools:

```text
crm.get_customer(customer_id)
crm.get_history(customer_id)
booking.check_availability(service_id, date, location?)
booking.create_booking(confirmed_booking_request, idempotency_key)
booking.reschedule_booking(booking_id, confirmed_new_slot, idempotency_key)
booking.cancel_booking(booking_id, confirmed_reason, idempotency_key)
tickets.create_support_ticket(customer_id?, session_id, issue, priority?)
tickets.get_ticket_status(ticket_id)
```

Actual tool execution must receive verified server-side `AuthContext` from session, **not trust arbitrary customer IDs supplied by a model**.

## Architectural flow

`LangGraph -> native tool OR MCP client -> MCP server (when chosen) -> application capability service -> provider port -> LocalAdapter | ExternalAdapter -> result canonicalization -> LangGraph`.

**Optimization:** For local deterministic workflows, direct domain-service calls may be preferable. Adding a remote MCP hop for every local lookup adds complexity/latency. MCP servers can reuse the same domain services without becoming the sole path.

## Provider switching contract

1. Same domain inputs/outputs and error semantics.
2. Feature capability negotiation: Google Calendar events do not necessarily equal staff/service/capacity booking rules.
3. Secure credentials and tenant separation when using external APIs.
4. Timezone-aware scheduling and concurrency conflict checks.
5. Idempotent write operations, retry and reconciliation strategies.
6. Integration contract tests run separately for each concrete implementation.
7. Availability of fallback must not accidentally create inconsistent duplicate records across backends.

## Provider risks

- OAuth scopes, token expiry, API pricing/rate limits, permission approvals and sandbox accounts.
- Calendar double-booking / races; model shouldn't set available slots by guessing.
- CRM personal data leakage and insufficient customer verification.
- Ticket duplicates, unassigned queues and unsafe 'resolved' status.
- MCP exposure and tool description injection; allowlisted tools and checked input schema.

## Acceptance examples

- Booking canceled twice with same idempotency key -> at most one change; user sees accurate status.
- CRM lookup without verified identity -> denied, no hidden data leaked.
- Ticket created -> human queue displays ticket ID/status; call outcome marked *escalated*, not *resolved*.
- External provider down -> explicit unavailable result and fallback/handoff, no fabricated success.
