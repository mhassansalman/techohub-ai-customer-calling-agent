# 03 — System Architecture (C4-inspired + Hexagonal)

## Architecture decision

Use a **modular monolith** for the initial implementation, with **ports-and-adapters** for channel, voice, knowledge, routing, business capabilities and storage. **LangGraph** coordinates application workflows; it does not replace access-control or transaction business rules.

The package includes companion diagrams: `01_END_TO_END_REQUEST_FLOW.png`, `02_COMPLETE_SYSTEM_NODES_EDGES.png`, `03_PROVIDER_PORTS_AND_MCP.png`, `04_ROUTER_AND_KNOWLEDGE.png`, `05_VOICE_LIFECYCLE.png`.

## C4 Level 1 — System context

**People:** customer, support agent, admin.  
**System:** AI Customer Calling Agent.  
**External systems (only when activated):** voice/telephony provider; external CRM; scheduler/calendar; helpdesk; hosted Jev/LLM/STT/TTS services.

## C4 Level 2 — Logical containers/modules

1. **Frontend:** React/Vite UI: chat, microphone, transcript, consent/display, staff review.
2. **API / channel adapter layer:** FastAPI HTTP + WebSocket, simulated telephone transport and later telephone adapters; session lifecycle.
3. **Voice processing services:** VAD (optional), STT (if incoming audio), TTS (if voice output); local/cloud provider ports.
4. **Application orchestration:** LangGraph state and conditional branches, `IntentRouter`, simple workflows, optional specialist agents, policy guards.
5. **Domain capabilities:** `KnowledgeProvider`, `CRMProvider`, `BookingProvider`, `TicketProvider` and application service implementations; native tools; optional MCP servers exposing selected calls.
6. **Persistence:** SQLite baseline; state checkpointing, session transcripts, audit and domain records; PostgreSQL extension later.
7. **Operations:** structured logs, correlation, metrics, errors, admin controls.

## Mandatory message lifecycle

`Inbound channel transport -> channel adapter/session + identity/context capture -> optional STT -> normalized CustomerMessage -> policy precheck -> IntentRouter -> LangGraph branch -> knowledge/business lookup or human handoff -> tool result -> response grounding/policy check -> action confirmation as needed -> AgentResponse -> optional TTS -> same channel.`

**Subtle but important:** Do **not** force raw microphone/telephone audio through the core LangGraph. Equally, do **not** remove the channel adapter just because STT happens early: it is responsible for session IDs, stream/call events, input validation, transport codecs and disconnects.

## Internal dependency direction

```text
api/channels ------> application/workflows ------> core/interfaces + core/models
   |                           |                              ^
   v                           v                              |
voice adapters         domain services / tools          concrete provider adapters
                               |
                         MCP exposure (optional boundary)
```

**Import rule:** `core` and `domain` may not import concrete Twilio, external CRM SDK, FastAPI, ChromaDB or MCP server packages. Concrete adapters depend on abstract ports; application wiring chooses one. MCP exposure is an alternative integration surface, not an intrinsic requirement for a local function.

## Core conceptual interfaces (illustrative, not implementation)

```python
from typing import Protocol

class IntentRouter(Protocol):
    async def classify(self, request: "CustomerMessage") -> "RoutingDecision": ...

class KnowledgeProvider(Protocol):
    async def search(self, query: str, limit: int = 5) -> list["Evidence"]: ...
    async def get_document(self, document_id: str) -> "KnowledgeDocument": ...

class CRMProvider(Protocol):
    async def get_customer(self, customer_id: str, auth: "AuthContext") -> "Customer": ...
    async def get_history(self, customer_id: str, auth: "AuthContext") -> list["Interaction"]: ...

class BookingProvider(Protocol):
    async def available_slots(self, query: "SlotQuery") -> list["Slot"]: ...
    async def create_booking(self, request: "BookingRequest", auth: "AuthContext") -> "Booking": ...

class TicketProvider(Protocol):
    async def create_ticket(self, request: "TicketRequest", auth: "AuthContext") -> "Ticket": ...
    async def get_ticket(self, ticket_id: str, auth: "AuthContext") -> "Ticket": ...

class STTProvider(Protocol):
    async def transcribe(self, audio: "AudioInput") -> "TranscriptResult": ...

class TTSProvider(Protocol):
    async def synthesize(self, text: str, voice: "VoiceConfig") -> "AudioOutput": ...
```

In a concrete implementation replace all quoted names with Pydantic/dataclass models and versioned error types.

## Dependency injection and provider selection

Use explicit provider configuration, e.g. `CRM_BACKEND=local`, `KNOWLEDGE_BACKEND=okf`, `ROUTER_BACKEND=rules`, `STT_BACKEND=faster_whisper`. App startup composes services from registered provider factories; does not hard-code providers in LangGraph nodes.

## Layer boundary vs deployment boundary

- Initially: one process for API+LangGraph+local ports is acceptable; MCP servers may be subprocesses or local HTTP as an integration proof.
- Later: MCP, telephony and other integrations may be separate services, but distributed deployment is **not** required to prove architecture quality.
- Do not describe local adapters as 'scalable microservices' without implementation evidence.

## Execution guardrails

1. Automatic assistant disclosure and consent state before capturing recordings.
2. Policy/identity gate before private lookups; confirmation and idempotency before mutations.
3. Knowledge answer cites sources with version/ID; unknown -> clarify or handoff.
4. Fault handling per provider: timeout + explicit error states, no deceptive success messages.
5. Audit logs independent of agent discretionary calls.

## Infrastructure ownership

- **LangGraph** owns orchestration/checkpoints.
- **Domain services** own booking conflict checks, ticket lifecycles, customer authorization.
- **Adapter** owns provider request/response translation and transport-specific concerns.
- **MCP server** exposes approved tools and verifies permissions.
- **KnowledgeProvider** returns evidence, not final business policy authority.
- **Channel adapter** owns call/browser lifecycle, not intent reasoning.
