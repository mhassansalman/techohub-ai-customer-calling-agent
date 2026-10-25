# 16 — End-to-End Demo Conversation Scenarios

> **All business content here is illustrative, not an approved real company's prices/hours/policies.** Substitute verified knowledge and seeded mock records after choosing a business domain.

## Scenario A — Simple FAQ, no private data

**Customer:** 'What time do you close on Saturday?'  
**Router:** `faq_business_hours`, simple, low risk.  
**Execution:** `KnowledgeProvider.search('Saturday closing hours')` -> approved OKF document with source/version.  
**Assistant:** states verified closing time only if available, else says not known and offers help.  
**Persist:** transcript, intent, evidence reference, outcome answered/unknown.  
**No CRM, booking or specialist agent required.**

## Scenario B — Booking requires multiple turns and explicit confirmation

**Customer:** 'Can I book a service next Friday?'  
**Workflow:** collect service and preferred time/date (with time zone), `BookingProvider.available_slots`.  
**Assistant:** offers actual available options.  
**Customer:** selects one slot.  
**Workflow:** verify identity if needed and propose exact booking; wait for 'yes, confirm'.  
**Customer:** confirms.  
**Workflow:** `create_booking` via selected port, with idempotency key and fresh availability check.  
**Assistant:** gives booking ID only after backend confirms transaction; otherwise honest failure/handoff.

## Scenario C — Complex complaint involving all capabilities

**Customer:** 'I canceled but I was charged and nobody replied to my complaint.'  
**Router:** complaint + elevated complexity; policy safeguards.  
**Specialist:** gather missing facts; after identity verification check CRM history, booking cancellation and OKF refund policy; look up existing ticket to avoid duplicate.  
**Outcome:** summarize findings, create or update support ticket, queue for human; **no unauthorized refund promise**.  
**Audit:** tool requests, permission checks, evidence refs, ticket ID and 'escalated' outcome.

## Scenario D — Direct handoff

**Customer:** 'I need a real person.'  
**Pre-routing:** deterministic handoff indicator recognized.  
**Workflow:** enqueue support request / staff handoff; no specialized agent required.  
**Assistant:** state whether a human is immediately connected or only a ticket has been created.

## Scenario E — Low-quality audio

**Input:** noisy / cut-off speech.  
**Ingestion:** STT returns low quality or failure.  
**Workflow:** ask to repeat or type; refrain from account queries and mutations.  
**Persistent record:** no arbitrary guessed intent, voice-failure event logged.

## Scenario F — Unsupported policy or missing evidence

**Customer:** 'Can you guarantee a complete refund right now?'  
**Knowledge:** policy may not address guarantee.  
**Workflow:** no invented authority; explain limits and route human/ticket when appropriate.

## Scenario G — Telephony optional

**Input:** Twilio/SIP call event arrives and audio chunks stream; after STT normalized messages use the **same** LangGraph graph as web voice.  
**Output:** response text synthesized/encoded for chosen telecom channel.  
**Status:** architecture/optional test; not evidence of completed telephony integration.
