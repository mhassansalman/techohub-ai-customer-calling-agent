# Diagrams — Node-and-Edge Reading Guide

All diagrams are provided as **PNG** (easy viewing), **SVG** (scalable), and **Graphviz `.dot`** (editable source). These are design diagrams, not deployed runtime diagrams.

| # | Diagram | What to read it for |
|---|---|---|
| 01 | `01_END_TO_END_REQUEST_FLOW.png` | Start here; complete customer input -> STT -> LangGraph routing -> tools/agent/human -> response -> TTS/text |
| 02 | `02_COMPLETE_SYSTEM_NODES_EDGES.png` | One-screen master system: all important components, ports and decisions |
| 03 | `03_PROVIDER_PORTS_AND_MCP.png` | Why MCP is optional, where it sits relative to native services and local/external provider adapters |
| 04 | `04_JEV_ROUTING_AND_OKF_KNOWLEDGE.png` | TypeSafe Jev candidate/routing baseline vs OKF retrieval and future vector adapters |
| 05 | `05_VOICE_AND_CALL_LIFECYCLE.png` | Correct voice boundary: channel adapter before STT; normalized text before LangGraph |
| 06 | `06_BOOKING_CONFIRMATION_AND_ESCALATION.png` | Verified identity, no booking without confirmation, idempotency and human fallback |
| 07 | `07_LOGICAL_DATA_MODEL.png` | Conceptual ERD for customer, session, transcript, bookings, ticket, routing and audit |

## Color and line legend

- **Blue:** core interface or stable application node.
- **Green:** baseline preferred local provider or required safe evidence source.
- **Amber dashed:** future/experimental/conditional; NOT claimed implemented.
- **Red:** risk gate, clarification, permission or human escalation.
- **Solid line:** actual conceptual execution/data flow.
- **Dashed/dotted:** optional adapters, fallback or cross-cutting linkage (per labels).

## Documentation link

See `../02_Project_Documentation/03_SYSTEM_ARCHITECTURE.md` for the narrative explanation and `../02_Project_Documentation/12_ARCHITECTURE_DECISIONS_AND_OPEN_QUESTIONS.md` for current vs optional scope.
