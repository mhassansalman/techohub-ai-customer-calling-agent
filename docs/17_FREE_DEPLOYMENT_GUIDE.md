# 17 — Free Deployment Guide (Vercel + Neon)

> This guide configures a separate Vercel Hobby FastAPI backend and Vercel
> Hobby frontend, backed by Neon PostgreSQL Free. It documents deployment steps;
> it does not claim that a public backend or a live Neon connection has been
> deployed or tested. Review each provider's current quotas and plan terms before
> deploying; do not enable paid services or billing.

## Target architecture

| Component | Provider | Project configuration | Data |
|---|---|---|---|
| Source | GitHub | `mhassansalman/techohub-ai-customer-calling-agent`, `main` | Application source |
| Frontend | Vercel Hobby | Existing project; root directory `frontend` | Static React/Vite bundle |
| Backend | Vercel Hobby | Separate project; repository root | FastAPI Vercel Function |
| Database | Neon Free | PostgreSQL pooled connection | Sessions, messages, tickets, audit events |

Browser requests go to the backend's `/api` routes. SQLite remains the local
development default. The backend requires a PostgreSQL `DATABASE_URL` when it
runs on Vercel and never copies local SQLite data to Neon.

## Runtime configuration

- Vercel's Python runtime discovers FastAPI applications and supports a custom
  `module:app` entrypoint through `tool.vercel.entrypoint` in `pyproject.toml`.
  This repository configures `backend.main:app`.
- Root `requirements.txt` contains the production runtime dependencies,
  including `psycopg[binary]`; it excludes tests and the local semantic-ML stack.
  `requirements.lock.txt` remains the fuller local development/test environment.
- Vercel's Python bundle configuration excludes development environments,
  bytecode, local environment files, tests, and frontend sources. The inspected
  backend/fixture/knowledge source payload is 267,662 bytes; the actual Vercel
  dependency bundle has not been built or measured.
- Vercel routes requests to the FastAPI ASGI app. No rewrite is needed for
  `/health`, `/api/services`, or `/api/sessions/*`.
- Lifespan startup creates tables from the SQLAlchemy models. This is not a
  schema migration system; use a new/empty Neon database for this integration.
- Database connection URLs using `postgresql://` or `postgres://` are normalized
  to the installed psycopg 3 driver. TLS is required and the SQLAlchemy pool is
  capped at one connection with no overflow and connection pre-ping.
- Semantic RAG and MCP are forced off on Vercel. Deterministic service/OKF
  behavior remains available; lexical RAG is available only if explicitly
  enabled. Groq classification is optional, uses rules-first fallback, and is
  not required for startup.

Vercel runtime references:
[Python Runtime](https://vercel.com/docs/functions/runtimes/python) and
[FastAPI](https://vercel.com/docs/frameworks/backend/fastapi).

## 1. Create the separate Vercel backend project

1. In Vercel, choose **Add New → Project** and import
   `mhassansalman/techohub-ai-customer-calling-agent`.
2. Select the `main` production branch.
3. Keep the **Root Directory** at the repository root (`.` / blank), not
   `frontend`. This backend must be a separate project from the existing
   frontend project.
4. Let Vercel detect the Python/FastAPI runtime. Do not set a frontend
   framework, static output directory, or frontend build command.
5. Keep the default Python install/build behavior. Vercel installs from the
   root `requirements.txt`; `pyproject.toml` identifies `backend.main:app`.
   Do not add a custom Uvicorn start command.
6. Configure the environment variables below before the first production
   deployment. Do not copy the existing frontend project's `vercel.json` into
   this backend project.

The backend base URL will be similar to
`https://<backend-project>.vercel.app`. The frontend API base URL includes the
`/api` path suffix.

## 2. Configure Neon PostgreSQL

1. In Neon, open the existing project and select its **pooled** connection
   string for the production database. The hostname should identify the Neon
   pooler (commonly `-pooler` in the host); pooled connections are recommended
   for serverless functions.
2. Use the SSL-enabled connection string. Do not put its value in source,
   documentation, a command line, or a `VITE_*` variable.
3. In the Vercel backend project's **Settings → Environment Variables**, add
   `DATABASE_URL` for **Production** as a sensitive value. Set its value to the
   Neon pooled connection string. The application requires PostgreSQL on
   Vercel and fails startup if this variable is missing or points to SQLite.
4. Do not set a Neon credential in local development unless intentionally
   testing against Neon. Locally, an absent `DATABASE_URL` uses
   `./data/techohub.db`.

No local SQLite rows are migrated. Existing Neon tables are not altered by
`create_all`; use a new database for the initial deployment.

## 3. Set backend environment variables

Set these in the **backend Vercel project**, for the Production environment:

| Variable | Value | Handling |
|---|---|---|
| `DATABASE_URL` | Neon pooled PostgreSQL connection string | Secret |
| `GROQ_API_KEY` | Groq key, if enabling model-assisted classification | Secret; optional |
| `STAFF_API_KEY` | Independently generated high-entropy staff key | Secret |
| `TECHOHUB_RAG_ENABLED` | `false` | Non-secret |
| `TECHOHUB_RAG_PROVIDER` | `lexical` | Non-secret |
| `TECHOHUB_MCP_ENABLED` | `false` | Non-secret |
| `TECHOHUB_CORS_ORIGINS` | `https://techohub-ai-customer-calling-agent.vercel.app` | Non-secret |

Set `STAFF_API_KEY` even if no staff UI is deployed; staff endpoints fail closed
without it. The optional Groq key is used only for intent classification;
deterministic rules remain available when it is absent or the provider fails.
Do not set `GROQ_API_KEY`, `STAFF_API_KEY`, or `DATABASE_URL` as a `VITE_*`
variable, and do not manually define Vercel's `VERCEL` system variable.

The code also prevents wildcard CORS and disables MCP and semantic retrieval
when running on Vercel, even if a feature flag is accidentally changed.

## 4. Deploy and test the backend

1. Save the backend environment variables and deploy the `main` branch.
2. Check `GET https://<backend-project>.vercel.app/health`; expect HTTP 200 and
   `{"status":"ok"}`.
3. Check `GET https://<backend-project>.vercel.app/api/services`; expect the
   approved service catalog.
4. Confirm a missing/invalid `DATABASE_URL` prevents Vercel startup rather than
   falling back to an ephemeral SQLite file.
5. Confirm an unconfigured/wrong staff key cannot access `/api/staff/tickets`.

Do not use real customer data for a public academic demonstration. Vercel
serverless invocations can start separate processes; Neon is the shared source
of application state. No live database connectivity, persistence-across-cold-
starts, or public deployment has been verified as part of this repository task.

## 5. Update the existing frontend project

Leave the existing Vercel frontend project separate and unchanged except for
its environment value:

1. Open the existing frontend project's **Settings → Environment Variables**.
2. Set `VITE_API_BASE_URL` for **Production** to
   `https://<backend-project>.vercel.app/api` (replace the hostname with the
   deployed backend URL; include `/api`).
3. Do not put any backend secret in a `VITE_*` value. Vite variables are public
   browser configuration.
4. Redeploy the existing frontend so the new API URL is included in its build.

The React client already reads `VITE_API_BASE_URL`, forwards
`X-Session-Token` for session operations, and displays a safe error message
when API requests fail. The deployment does not require frontend source or
project-root changes.

## 6. Verify public chat/session continuity

From the deployed frontend:

1. Load the app and browse services.
2. Start a text conversation; the backend creates the session and returns a
   random per-session access token.
3. Send multiple messages, refresh or revisit the app only if the UI preserves
   the active session, and confirm the same backend session continues.
4. Verify session status, message submission, and ending require the matching
   `X-Session-Token`. A token from another session must receive HTTP 401.
5. Confirm support ticket creation remains idempotent for a customer message
   and staff list/detail endpoints require `X-Staff-API-Key`.
6. Check browser developer tools to ensure no credentials or session tokens
   appear in URLs or browser logs.

The session token is held in the existing React component's memory, not in a
URL or persistent browser storage. A full browser/API/Neon acceptance test must
be performed after deployment; automated local tests are not evidence of a
live deployment.

## Security and persistence notes

- `X-Session-Token` is required for session reads, message submission, and
  session termination. Possession of a session UUID alone is insufficient.
- Staff endpoints require `STAFF_API_KEY`; missing configuration returns 503
  and invalid credentials return 401.
- Production CORS must use the exact frontend origin above, without a wildcard.
- Secrets are server-side environment variables and are not exposed in the
  frontend bundle or logged by the application.
- PostgreSQL persists session records, messages, availability context, tickets,
  and audit events in shared Neon storage. The integration does not migrate
  local data, and no Neon persistence test has been performed yet.
- Database tables are created by SQLAlchemy `create_all` on application
  startup. There is no migration tool configured for this deployment.
- Semantic embeddings/model packages are omitted from the Vercel runtime
  requirements. No model is downloaded at startup; MCP remains disabled.
- Free-tier availability, quotas, and limits may change. Stay within the
  selected free plans and do not enable paid compute or services.

## Verification performed locally

| Check | Result |
|---|---|
| Full backend pytest suite | 420 passed |
| Focused database-engine and session-security regressions | 27 passed |
| PostgreSQL dialect model DDL compilation | Passed; no real PostgreSQL connection |
| Frontend Vitest | 97 passed |
| Frontend production build | Passed; JavaScript bundle 262.07 kB (79.61 kB gzip) |
| Backend source/data payload | 267,662 bytes excluding local environments and bytecode; dependency bundle not built |
| Python compilation | Passed |
| `vercel.json` and `pyproject.toml` parsing | Passed |
| `git diff --check` | Passed |

These local checks do not prove a live Neon connection, a public backend
deployment, Vercel production behavior, or a public end-to-end session.
