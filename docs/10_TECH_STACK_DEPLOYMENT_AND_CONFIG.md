# 10 — Tech Stack, Local Deployment, Configuration

## Stack status

| Category | Preferred implementation | Commitment |
|---|---|---|
| Language | Python 3.12+ | Proposed baseline |
| API | FastAPI + Pydantic | Proposed baseline |
| Graph | LangGraph; LangChain for useful integration utilities | Architectural selection |
| DB | SQLite + SQLAlchemy; Alembic migrations | Proposed baseline |
| Frontend | React/Vite + Tailwind CSS | Proposed baseline |
| Knowledge | OKF Markdown bundle; no vector DB in first cut | Architecture selected |
| LLM | Ollama/local model if machine can run it; external adapter possible | Hardware test required |
| Intent | `IntentRouter` with rules baseline, Jev candidate, structured LLM fallback | Port selected; Jev integration conditional |
| STT | faster-whisper / browser-supported approach | Benchmark required |
| TTS | Piper/browser speech synthesis | Benchmark required |
| Voice transport | WebSockets for browser sessions | Proposed |
| MCP | Python MCP SDK / FastMCP pattern for approved capabilities | Integration scope targeted |
| Testing | pytest, pytest-asyncio, HTTPX, mocked providers | Strong recommendation |
| Quality | Ruff, formatting, typing, CI (GitHub Actions optional) | Strong recommendation |
| Telephony | Twilio or SIP adapters; SIM experimental | Future/optional |
| Deployment | Local host, no Docker required | Preferred initial constraint |

## Why start without Docker?

The discussion explicitly favors a no-Docker local development path due to the user's machine limitations. Use a virtual environment, local SQLite and separately started frontend/backend; containerization can be documented as future work without blocking demonstration.

## Example environment variables (template, no real secrets)

```dotenv
APP_ENV=development
DATABASE_URL=sqlite+aiosqlite:///./data/app.db
KNOWLEDGE_PROVIDER=okf
OKF_BUNDLE_PATH=./knowledge_bundle
ROUTER_PROVIDER=rules
CRM_PROVIDER=local
BOOKING_PROVIDER=local
TICKET_PROVIDER=local
STT_PROVIDER=faster_whisper
TTS_PROVIDER=browser
LLM_PROVIDER=ollama
LLM_MODEL=<validated-local-model>
SESSION_RETENTION_DAYS=<define-after-policy-review>
ENABLE_TWILIO=false
ENABLE_EXTERNAL_ADAPTERS=false
```

`JEV_API_KEY`, `TWILIO_AUTH_TOKEN`, calendar credentials and similar values must come from environment/secret manager when enabled; never commit them. Config names are **illustrative** pending actual code.

## Proposed repository layout

```text
ai-customer-calling-agent/
  backend/
    api/
    core/{models,interfaces,policies}/
    application/{workflows,agents,services,tools}/
    adapters/{channels,speech,llm,routers,knowledge,crm,booking,tickets}/
    mcp_servers/
    persistence/
    config/
  frontend/
  knowledge_bundle/{index.md,faq,policies,procedures}/
  tests/{unit,contract,integration,e2e,security,fixtures}/
  docs/
  diagrams/
  scripts/
  .env.example
  README.md
```

## Portable setup outline (not tested commands)

1. Install supported Python and Node LTS locally.
2. Create venv `python -m venv .venv`; activate per OS.
3. Install backend dependencies from requirements/pyproject after creation.
4. Configure `.env` from `.env.example`, generate test SQLite database with migrations, add approved mock knowledge.
5. Start local backend (e.g. `uvicorn backend.api.main:app --reload`) and frontend (`npm run dev`) once application entrypoints exist.
6. Run pytest and a smoke test covering text and browser voice before trying any external API.

**Do not claim the commands above already run:** repository implementation isn't part of this pack.

## Provider feature flags and adapters

Use explicit provider registry and healthcheck. When optional external adapter is disabled or unavailable, either default to the configured local provider or report unavailable; silent switching that could duplicate authoritative records is forbidden.

## Questions to benchmark first

Available RAM/CPU/GPU, preferred English/Urdu, STT response delay, local LLM token speed, TTS startup latency, microphone quality and browser permissions. Choose final model/provider after local measurements.
