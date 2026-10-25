# 01 — Project Charter, Business Problem and Scope

## Project identity

**Working title:** AI Customer Calling Agent  
**Type:** University software engineering project, Project 2 of supplied assignment  
**Product vision:** An automated, transparent, auditable customer-service agent that answers verified questions, performs permitted self-service actions and escalates uncertain/complex issues via text, browser voice and (eventually) telephone.

## Authoritative assignment interpretation

The university brief calls for a *voice-based assistant* able to conduct limited customer-service conversations, retrieve answers from an approved FAQ/knowledge base, log conversation outcome and safely escalate. **A simulated call/browser-based voice demo is explicitly acceptable**. Mandatory: start/end session, transcript, speech-to-text and text-to-speech with text fallback, **at least three intents**, logging of date/time, transcript or permitted summary, intent and outcome, human handoff, automated-agent disclosure, and no unauthorized commitments. Real telephony, CRM, booking, multilingual, sentiment analysis are **optional advanced features**. Source: user-supplied `Student_Software_Project_Assignments(1).pdf`, Project 2 pp. 3 and submission/rubric p. 7 (PDF page numbering may differ).

## Users and actors

- **Customer:** asks general questions, accesses own information after verification, requests/reschedules bookings and human assistance.
- **Human support operator:** receives escalations, checks tickets and concludes unresolved cases.
- **Business administrator:** manages permitted knowledge, services, hours, booking availability and users.
- **Student/developer/tester:** configures local mock services and runs demo/test scenarios.
- **External providers:** third-party CRM/calendar/helpdesk, STT/TTS/LLM and telecom services, via adapters only.

## Problem statement

Customer-service teams repeat routine explanations and lookups, but fully autonomous systems can hallucinate policy, misidentify the caller, create duplicate transactions, or mishandle complex issues. The project provides a constrained assistant that makes routine questions self-service while preserving accuracy, traceability and human oversight.

## Core outcomes

1. Natural customer interaction through typed chat or microphone, with a usable fallback when speech fails.
2. Grounded answers from approved business knowledge; cited source identifiers and safe `unknown` outcomes.
3. Customer record lookup/booking/ticket management through independent provider interfaces.
4. Controlled routing: simple task -> deterministic tool workflow; complex -> specialized agent; high-risk/uncertain -> human escalation.
5. Persisted conversation states, timestamps, intents, actions, outcomes and audit details.
6. Change provider/channel implementation without changing application-domain models and LangGraph logic.

## Scope — committed vs planned

### Mandatory assignment MVP

- Business scope and sample dialogues; three approved intents (proposed: business FAQ/hours, appointment lookup/booking, human escalation; exact three set after business domain is chosen).
- Start/end session; live transcript (with consent/privacy rules); text fallback.
- Browser microphone transcription (STT) and speech playback (TTS).
- Authorized FAQ lookup using a small curated OKF-based knowledge bundle.
- Intent detection, fallback, outcome logging and handoff.
- Safe user-facing disclosure: 'I am an automated assistant.'
- Test cases for valid, invalid, noisy and unsupported requests; setup instructions; demo.

### Planned engineering depth / enhancement targets

- Locally implemented CRM, appointment management and ticket management, each behind a provider interface.
- Scoped MCP servers (or tool exposure) for business capabilities where justified.
- LangGraph-based multi-turn orchestration, policy gates, simple workflow and specialized agent boundary.
- Status dashboard for staff; lightweight customer records and tickets.
- Contextual response verification, observability and reproducible integration contracts.

### Optional extensions, not automatically deliverables

- A concrete third-party CRM/calendar/helpdesk adapter (select one proof of concept, if time permits).
- TypeSafe Jev as the route classifier (requires access/cost/performance validation).
- Multi-language English/Urdu, streaming voice, interruption/barge-in, richer sentiment analytics.
- Twilio/SIP real phone calls and SIM/GSM experimental connectivity.
- Cloud provider fallbacks, PostgreSQL, vector-search adapters, containerized deployment.

## Non-goals

- A fully autonomous billing/refund authorization system.
- Unlimited enterprise customer-service coverage or automatic legal/medical/financial advice.
- Unverified promises, transactions or access to records based only on an unverified calling number.
- Building full replicas of Salesforce, Calendly or Zendesk.
- Claiming architecture-supported integrations are already delivered.

## Product assumptions requiring confirmation

- The **business domain is undecided**; no company-specific policy or price should be invented.
- Local machine capacity and budget are unknown; local models require benchmark before commitment.
- Need no Docker for the first implementation; Docker may be revisited later.
- The team's exact availability, start date and time limits must be asked in the timeline-planning chat.

## Done means

- Mandatory assignment demo genuinely works end to end, with evidence: tests, code, diagrams, screenshots, log records, README and 3–5 minute recording or live walkthrough.
- Optional features are called implemented only when their tests and demo evidence exist.
