# 14 — Assignment Rubric (100 Marks), Submission Traceability

**Authoritative source:** `Student_Software_Project_Assignments(1).pdf`, Project 2 and general submission/rubric. The table below reproduces the *rubric category/marks*, then adds **proposed evidence**, not instructor-specific guarantees.

| Assessment category | Marks | What we need to show |
|---|---:|---|
| Problem understanding & requirements | 10 | Selected business, user journeys, scope/out-of-scope, SRS, three defined intents |
| Design & architecture | 15 | End-to-end flow, C4/ports-and-adapters view, DB schema and design decisions |
| Core functionality & completeness | 30 | Actual working voice+text fallback, FAQ retrieval, 3 intents, session log, safe handoff |
| Code quality & appropriate technology | 15 | Modular code, typed contracts, dependency injection, validated errors, readable README |
| Testing & error/limitation handling | 10 | Unit, integration and voice/noisy/unsupported tests, failure/limitations report |
| Documentation & setup | 10 | Source + README, installation/dependencies, API + data schemas, screenshots, decisions |
| Demonstration & explanation | 10 | Live demo or 3–5 minute recording, successful and failure scenario explanation |
| **Total** | **100** | No score guaranteed by any feature count |

## Requirements -> evidence traceability

| Assignment requirement | Required evidence |
|---|---|
| Voice conversation flow | Mic capture + STT transcript + TTS playback demo |
| Text fallback | UI screenshot and demonstration |
| At least three defined intents | Test corpus and separate working end-to-end runs |
| Approved FAQ knowledge base | OKF bundle with approved sample content and retrieved source references |
| Session start/end + transcript | Test assertions + staff log UI |
| Session date/time, intent, outcome | DB snapshot/screenshot or API response |
| Uncertain/sensitive/unsupported handoff | Explicit escalation test and resulting ticket/queue record |
| Automated assistant disclosure | Start-of-call transcript |
| No unauthorized commitments | Refund/booking rejection and confirmation tests |
| Database/architecture | Logical ER diagram and nodes/edges flowchart |
| Code and README | Clean repository, dependencies and exact commands |
| Tests + limitations | Results with failed/fixed cases, future extension boundaries |
| Demo | Recorded or live walkthrough within assignment format |

## Recommended submission archive structure

```text
submission/
  README.md
  source/
  docs/
    project_charter.md
    srs.md
    architecture.md
    database_schema.md
    api_contracts.md
    design_decisions.md
    test_cases_and_results.md
    limitations.md
    final_report.md
  screenshots/
  demo/video_link.txt
  data/sample_knowledge_bundle/
```

## Important grading positioning

- MCP, Jev, multiple agents, CRM and telephony are not mandatory by the university assignment; they are architecture and differentiation, **never substitutes for mandatory functionality**.
- A tested single-agent/workflow system often demonstrates engineering competence better than three untested agents.
- Do not claim that a PNG or `.md` alone establishes working feature completion.
- The third-party technologies used must be listed and credited per assignment guidelines.
