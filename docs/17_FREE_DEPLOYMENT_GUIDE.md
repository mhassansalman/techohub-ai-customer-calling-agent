# 17 — Free Deployment Guide (Render + Vercel)

> Academic demonstration deployment. Budget: $0. No paid services, domains, or
> infrastructure. This guide prepares the repository for public access; it does
> not perform the public deployment itself.

## Target architecture

| Tier | Provider | Plan | Cost | Purpose |
|------|----------|------|------|---------|
| Source | GitHub | Free | $0 | Git repository (`main`) |
| Backend | Render | Free ($0/mo) | $0 | FastAPI app, HTTPS by Render |
| Frontend | Vercel | Hobby | $0 | React/Vite build, HTTPS by Vercel |

Data flow: browser (Vercel HTTPS) → `VITE_API_BASE_URL` → Render backend HTTPS → SQLite (ephemeral) / Groq (optional, key never reaches browser).

## Prerequisites

- GitHub repository: `mhassansalman/techohub-ai-customer-calling-agent`, branch `main`.
- Render account connected to the GitHub repo.
- Vercel account connected to the same GitHub repo.
- Backend secret `GROQ_API_KEY` and `STAFF_API_KEY` available (Render secret UI).
- No billing/credit card on either platform (free tiers only).

## Files added/changed for deployment

- `render.yaml` — reproducible Render service definition (build/start commands, env vars, health check).
- `requirements.render.txt` — lighter Render dependency set (excludes torch/sentence-transformers/transformers; semantic RAG disabled on Render Free).
- `frontend/vercel.json` — declares Vite framework, build command, output directory.
- `.env.example` — environment variable names only, no real secrets.
- `docs/17_FREE_DEPLOYMENT_GUIDE.md` — this guide.
- `tests/test_session_security.py` — per-session access token regression tests.
- `frontend/src/api.test.js` — `VITE_API_BASE_URL` configuration tests.
- `backend/main.py`, `backend/models.py`, `backend/schemas.py`, `frontend/src/App.jsx`, `frontend/src/api.js` — session authorization + API base URL.

## Render backend settings

Create a **New Web Service** → "Build and deploy from a Git repository".

| Setting | Value |
|---------|-------|
| Repository | `mhassansalman/techohub-ai-customer-calling-agent` |
| Branch | `main` |
| Region | Ohio (US East) |
| Compute | Free ($0/month) |
| Root Directory | blank (repository root) |
| Build Command | `pip install -r requirements.render.txt` |
| Start Command | `python -m uvicorn backend.main:create_app --factory --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` |
| Auto Deploy | On (after manual verification) |

### Render environment variables

| Variable | Value | Secret? |
|----------|-------|---------|
| `GROQ_API_KEY` | your Groq key | Yes (Render secret UI, `sync: false`) |
| `STAFF_API_KEY` | your staff key | Yes (Render secret UI) |
| `TECHOHUB_RAG_ENABLED` | `false` | No |
| `TECHOHUB_RAG_PROVIDER` | `lexical` | No |
| `TECHOHUB_MCP_ENABLED` | `false` | No |
| `TECHOHUB_CORS_ORIGINS` | `<Vercel HTTPS URL>` after frontend deploy | No |
| `DATABASE_URL` | (omit → ephemeral `./data/techohub.db`) | No |

Render Free constraints honored: ephemeral filesystem (SQLite lost on redeploy/restart), no large model downloads at startup (RAG disabled, sentence-transformers import is lazy), no paid inference at startup, bounded Groq retries with rules-first fallback.

### Health check

`GET /health` → `{"status": "ok"}` (HTTP 200). No session token required.

## Vercel frontend settings

Create a **New Project** → import the same GitHub repo.

| Setting | Value |
|---------|-------|
| Framework Preset | Vite |
| Root Directory | `frontend` |
| Production Branch | `main` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Install Command | `npm install` (or `npm ci`) |

### Vercel environment variable

| Variable | Value | Secret? |
|----------|-------|---------|
| `VITE_API_BASE_URL` | Render backend public HTTPS URL | No (public browser config) |

No `GROQ_API_KEY` or `STAFF_API_KEY` in Vercel. `VITE_*` variables are public browser configuration.

## Critical post-deployment step

Render's CORS allow-list defaults to empty (no cross-origin traffic). After the Vercel frontend has a public HTTPS URL:

1. Open the Render service → Environment Variables.
2. Set `TECHOHUB_CORS_ORIGINS` to the Vercel frontend HTTPS URL (e.g. `https://techohub.vercel.app`).
3. Save and redeploy the Render backend.

Without this, the browser cannot call the Render API from the Vercel origin.

## Session security (public-demo authorization)

- A per-session access token (`token_urlsafe(32)`) is issued at session start and returned in the `POST /api/sessions` response (`access_token`).
- The public session UUID alone does NOT authorize reads/writes/termination.
- `X-Session-Token` header is required on `GET /api/sessions/{id}`, `POST /api/sessions/{id}/messages`, and `POST /api/sessions/{id}/end`.
- Tokens are compared with `secrets.compare_digest`, never placed in URLs, never logged, not persisted to browser storage (kept in a React ref).
- Cross-session access with another session's token returns HTTP 401.
- Staff ticket endpoints are protected by `STAFF_API_KEY` (HTTP 503 if unconfigured, 401 if wrong).
- Groq credentials and staff secrets are never exposed to the frontend.
- CORS is restrictive by default (no origins unless `TECHOHUB_CORS_ORIGINS` is set).

Regression tests: `tests/test_session_security.py` (7 tests, live FastAPI TestClient request paths) plus token forwarding across `tests/test_api_sessions.py` and `tests/test_workflow.py`.

## Persistence (SQLite, ephemeral on Render Free)

- Default database: `./data/techohub.db`, created automatically at startup (`Base.metadata.create_all`).
- Render Free filesystem is ephemeral: conversation history, tickets, and session state may disappear on redeploy, restart, or instance sleep.
- This is an academic demo; no production durability is claimed. No real customer information should be used.
- No migrations introduced; schema derives from SQLAlchemy models.

## Verification (local, pre-deployment)

| Check | Result |
|-------|--------|
| Backend pytest (full suite) | 400 passed |
| Security tests (`test_session_security.py`) | 7 passed |
| Frontend Vitest | 93 passed |
| Frontend production build | passed |
| Python compileall | passed |
| `git diff --check` | clean |
| Render start command smoke test (`/health`) | HTTP 200 `{"status":"ok"}` |
| Committed secrets | none |

## Known limitations

- Render Free cold starts after inactivity (first request may be slow).
- SQLite data is not durable across Render redeploys/restarts.
- Semantic RAG and MCP are disabled on Render Free (CPU/RAM); preserved locally.
- No custom domain; HTTPS provided by Render/Vercel subdomains.
- Dependent on public-demo session-token authorization, not a full user-account system.

## Deployment order

1. Push and merge deployment changes to `main`.
2. Deploy Render backend; verify `GET /health`.
3. Deploy Vercel frontend using Render's public HTTPS URL as `VITE_API_BASE_URL`.
4. Set Render `TECHOHUB_CORS_ORIGINS` to the Vercel URL; redeploy backend.
5. Verify public end-to-end: create session, send message, end session (each with the session token).

## Manual steps by platform

**GitHub:** push `feature/free-deployment` to origin and open a merge/pull request into `main` (requires permission; not done in this session).

**Render:** create web service with the settings above; add secret env vars; verify `/health`; after Vercel deploy, set `TECHOHUB_CORS_ORIGINS`.

**Vercel:** import repo, root directory `frontend`, set `VITE_API_BASE_URL` to Render URL, deploy.

**End-to-end test:** open the Vercel URL, start a conversation (Message/Mic/Live Call/Call-Only), confirm the backend is reachable, and end the session.
