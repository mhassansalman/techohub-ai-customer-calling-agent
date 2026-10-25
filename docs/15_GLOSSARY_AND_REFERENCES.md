# 15 — Glossary, Corrections and References

## Glossary

| Term | Practical definition in this project |
|---|---|
| Agent | Component capable of reasoning/planning across bounded permitted tools/steps |
| Simple workflow | Fixed, testable sequence of validated tool calls and policy gates |
| LangGraph | Graph/state orchestration library; owns conditional control flow and checkpoints |
| Native tool | Internal application function/tool accessible directly to workflow/agent |
| MCP | Model Context Protocol: a standardized way to expose scoped tools/resources to AI clients; not business logic or 'better' by default |
| Provider port | Stable interface the application depends on, implemented by adapters |
| Adapter | Concrete provider/transport-specific implementation of a port |
| CRM | Customer identity/profile and interaction-history capability |
| Booking | Available slots and committed appointment transaction capability |
| Ticket | Case-management queue for unresolved issues and follow-up |
| OKF | Open Knowledge Format, organized Markdown with index and typed frontmatter |
| RAG | Retrieval-Augmented Generation, using retrieved trusted information to ground generated output |
| ChromaDB | Vector DB candidate for future semantic retrieval adapter |
| FAISS | Vector similarity search library candidate for future custom retrieval adapter |
| Milvus | Vector database candidate for future high-scale retrieval adapter |
| Jev | TypeSafe AI **decision model** for bounded typed judgments; suitable for intent/complexity routing; does not generate full natural-language answers |
| STT | Speech-to-text transcription |
| TTS | Text-to-speech synthesis |
| VAD | Voice activity detection, detects speech/silence boundaries |
| SIP | Session Initiation Protocol for VoIP telephony signaling |
| Idempotency | Ensuring repeat network calls/retries don't accidentally repeat a transaction |
| Handoff | Controlled transfer or queued follow-up by a human operator |
| Schema/contract | Provider-independent definitions of fields, allowed states, errors and semantics |

## Corrections recorded from conversation

1. Earlier chat mistakenly described Jev primarily as a structured output format. **Correct:** Jev is a decision/classification model; a `RoutingDecision` JSON/Pydantic schema is our **own** contract for all routing implementations.
2. OKF is **not** a vector DB and isn't synonymous with all RAG. It is a portable structured knowledge format. The OKF adapter can retrieve docs without vectors; grounding generation from those documents remains retrieval augmentation.
3. `ExternalAdapter` in a diagram means **support via interface** until code/testing confirm implementation. In particular ChromaDB, FAISS, Milvus and telephony are out of baseline scope.
4. The channel adapter handles transport and session *before* optional STT; the AI core sees normalized text. This is the final agreed voice-boundary sequence.

## Primary sources (checked October 17, 2026)

- University project brief provided by user: `Student_Software_Project_Assignments(1).pdf`, Project 2, general submission and rubric.
- Official OKF site and spec overview: https://okf.md/
- OKF FAQ: https://okf.md/faq/
- Official TypeSafe Jev intent routing: https://docs.typesafe.ai/patterns/intent-routing
- LangChain / LangGraph + Jev technical explanation: https://www.langchain.com/blog/building-prod-with-jev-and-langgraph

## Limits

Provider prices/quotas are not fixed in this document and require a fresh provider check before use. Jev API format/version must be verified against current official SDK/docs when implementing. Schema examples are design proposals; no runtime evidence supplied.
