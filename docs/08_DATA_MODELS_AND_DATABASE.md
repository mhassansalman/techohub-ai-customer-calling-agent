# 08 — Logical Data Model & Database Schema

## Storage design

Use SQLite + SQLAlchemy during local prototype. Logical domain contracts must stay neutral so PostgreSQL or external CRM/calendar/helpdesk services may be introduced independently. This is a **logical schema**, not applied migrations.

## Entities

| Entity | Key fields | Notes |
|---|---|---|
| `Customer` | `id`, `display_name`, `contact_hash_or_masked`, `created_at`, `status` | Minimize PII; verified identity separate from displayed name |
| `Interaction` | `id`, `customer_id?`, `session_id`, `summary`, `timestamp`, `source` | CRM history link; consent-sensitive |
| `ConversationSession` | `id`, `channel`, `started_at`, `ended_at?`, `consent_state`, `auth_state`, `outcome`, `customer_id?` | Mandatory logging anchored here |
| `Message` | `id`, `session_id`, `role`, `text`, `timestamp`, `language`, `asr_confidence?`, `retained` | PII redaction/retention applies |
| `RouteDecision` | `id`, `message_id`, `router_provider`, `intent`, `complexity`, `risk`, `confidence?`, `chosen_handler` | Observability, not proof of authorization |
| `KnowledgeDocument` | `id`, `version`, `source_path`, `title`, `status`, `effective_at?` | Metadata from OKF; content may remain on filesystem |
| `EvidenceReference` | `id`, `message_id`, `document_id`, `document_version`, `section?` | Explain answer provenance |
| `Service` | `id`, `name`, `duration_minutes`, `active`, `location_id?` | Business domain-specific options TBD |
| `AvailabilitySlot` | `id`, `service_id`, `staff_id?`, `starts_at`, `ends_at`, `capacity` | UTC storage + business time zone rendering |
| `Appointment` | `id`, `customer_id`, `service_id`, `starts_at`, `ends_at`, `status`, `provider_ref?` | Unique constraint/transaction guard needed |
| `SupportTicket` | `id`, `customer_id?`, `session_id?`, `category`, `priority`, `status`, `assigned_to?`, `summary`, `created_at`, `updated_at` | Unresolved work, unlike CRM profile |
| `ActionRequest` | `id`, `session_id`, `action_type`, `payload_hash`, `confirmation_state`, `idempotency_key`, `provider_result_ref?` | Prevent premature/duplicate mutations |
| `AuditEvent` | `id`, `trace_id`, `actor`, `action`, `resource_type`, `resource_id?`, `outcome`, `timestamp` | Do not log secrets or raw sensitive content |
| `UserOperator` | `id`, `role`, `active` | Staff authorization, escalation routing |

## Key relations

- `Customer 1 -> many ConversationSession, Appointment, Interaction, SupportTicket` (some records intentionally anonymous).
- `ConversationSession 1 -> many Message, RouteDecision (via Message), ActionRequest, AuditEvent`.
- `SupportTicket many -> optional Customer and optional ConversationSession`; ticket doesn't imply immediate resolution.
- `Service 1 -> many Appointment`; slot/capacity constraints checked atomically.
- `Message many -> EvidenceReference`; evidence points to versioned OKF knowledge.

## Proposed enums

- `SessionOutcome`: answered, booked, escalated, unresolved, disconnected, cancelled, failed.
- `TicketStatus`: open, triaged, waiting_customer, in_progress, resolved, closed.
- `BookingStatus`: proposed, confirmed, cancelled, rescheduled, failed.
- `ConsentStatus`: unknown, granted, denied; if recording required and denied, no recording.
- `AuthStatus`: anonymous, pending, verified, failed.
- `ActionConfirmation`: proposed, awaiting_confirmation, confirmed, rejected, expired, executed, failed.

## Multi-tenant consideration

If demo supports multiple businesses, **tenant_id** must exist on all customer, document and operational records, and provider factories must be configured by tenant. Otherwise explicitly declare single-business prototype and avoid fake multi-tenancy claims.

## Recommended invariants

1. Customer-specific lookup requires authorized identity context (not merely passing `customer_id`).
2. Appointment creation enforces availability and idempotency inside database/provider implementation.
3. Timestamp stored UTC and displayed in business/customer time zone.
4. Transcript/raw audio retention and audit policy documented; avoid raw audio unless essential and consented.
5. External adapter's `provider_ref` and internal IDs never conflated.
6. Ticket status transitions validated; no LLM arbitrary transitions.

## Data migration strategy

SQLite/Alembic migration baseline; optionally switch to PostgreSQL using SQLAlchemy driver. CRM provider migration to external SaaS needs reconciliation/unique mapping: it is not equivalent to simply swapping a database URL.
