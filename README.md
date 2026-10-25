# TECHOHUB AI Customer Calling Agent

An academic prototype of a transparent, knowledge-grounded customer-service
assistant for a fictional salon. The local backend includes persistent session
lifecycle endpoints and an internal deterministic knowledge service.

## Scope

- **P0 (mandatory):** implement the required Week 1 and subsequent core
  deliverables in the traceable backlog.
- **P1 (optional):** pursue enhancements only after P0 priorities and approvals.
- **P2 (excluded):** do not implement excluded-scope features.

The Week 1 task IDs, dependencies, and linked acceptance evidence are in
[the traceable backlog](assignment/02_Traceable_Backlog_and_Daily_Schedule.md)
and [the machine-readable task backlog](assignment/task_backlog.json).

## Local setup

Requirements: Python 3.12 and Node.js/npm for the planned browser client.
Docker is not required.

From PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt
```

In Git Bash:

```bash
py -3.12 -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt
```

If PowerShell activation is restricted, run the environment directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
```

`requirements.in` records the direct Week 1 Python dependencies;
`requirements.lock.txt` pins the resolved environment. Frontend dependencies
are pinned in `frontend/package.json` and `frontend/package-lock.json`. Install
them from PowerShell with:

```powershell
Push-Location frontend
npm.cmd ci
Pop-Location
```

The P12 browser text chat is a standalone client of the existing session
lifecycle API. The API currently records turns and returns an explicit interim
message; knowledge, availability, handoff, and other capability responses
remain deferred to P13 orchestration. The compatibility page below remains a
separate P03 spike.
Do not commit `.env` files, credentials, local databases, or generated
recordings.

## Backend scaffold

The FastAPI application currently exposes the session lifecycle API below.
Start it from the repository root after installing the Python dependencies:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

### Session lifecycle API

- `POST /api/sessions` — create a session and persist the automated-assistant
  disclosure.
- `POST /api/sessions/{session_id}/messages` — persist a normalized text turn
  and return an explicit interim response until AI generation is implemented.
- `POST /api/sessions/{session_id}/end` — close an active session with a
  documented outcome.
- `GET /api/sessions/{session_id}` — return session status and record counts,
  not transcript content.

### Run the P12 browser text chat

Run the backend from the repository root in one PowerShell terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, start the Vite development server:

```powershell
Push-Location frontend
npm.cmd ci
npm.cmd run dev
Pop-Location
```

Open the local URL printed by Vite (by default `http://127.0.0.1:5173`).
The development server proxies `/api` requests to `127.0.0.1:8000`; no API
key or provider credential is sent to the browser. Run the frontend tests and
production build from the `frontend` directory with `npm.cmd test` and
`npm.cmd run build`.

Session history can be read by the persistence layer for tests and trusted
application code. A transcript-reading HTTP endpoint is intentionally absent
until staff access control is implemented. The default local SQLite database
is `data/techohub.db`; it is ignored by Git.

### Internal knowledge service

`backend.knowledge.KnowledgeService` provides deterministic, source-traceable
answers using the approved Demo Salon fixture for operating hours and catalog
services. It safely abstains on unsupported policies and appointment-slot
questions. No approved FAQ Markdown bundle currently exists, so no policy
answers are available. An optional OKF bundle can be loaded from an
`index.md`; only index-linked, frontmatter-marked approved FAQ records are
eligible. This internal service is not yet connected to the session API or an
intent router.

`backend.availability.AvailabilityService` returns only recorded canonical
fixture slots and explicitly labels them as fixture data, not live calendar
availability. `AvailabilityConversationService` supports the deterministic
Friday-to-Saturday correction through session-scoped context persisted in
SQLite. The context stores only the selected service and requested date; it is
isolated by session and survives a process/database reconnection. The service
does not create, modify, or cancel appointments and is not connected to the
session API or intent router yet.

### Internal intent classification

`backend.intent.RuleFirstIntentClassifier` classifies supported requests with
deterministic rules first and uses the Groq adapter only when a safe local
classification cannot be established. Provider output is validated locally
with Pydantic; classification does not answer requests, invoke tools, or
integrate with the session API or a LangGraph workflow.

Groq configuration is optional for local rules and tests. To enable model
classification, set `GROQ_API_KEY` in the ignored local `.env` file or process
environment. `GROQ_MODEL` defaults to `openai/gpt-oss-20b`;
`GROQ_TIMEOUT_SECONDS`, `GROQ_MAX_RETRIES`, `GROQ_TOTAL_DEADLINE_SECONDS`, and
`GROQ_BACKOFF_SECONDS` can tune the bounded retry policy (at most one retry,
five seconds per attempt, and eight seconds total). Never commit `.env` or
include the key in logs or command-line arguments.

## P03 Chrome voice compatibility check

This is a manual browser capability check, not a production voice integration.
From the repository root, start the static test page:

```powershell
py -3.12 -m http.server 8765 --directory frontend
```

Open `http://localhost:8765/voice-compatibility.html` in Google Chrome. Allow
microphone permission, test recognition using only the displayed harmless
phrase, and use “Speak text” to verify audible output. Record the Chrome
version, permission outcome, exact recognition result/error, and whether TTS
was audible. Chrome speech recognition may use an online browser service; do
not use personal or customer data. The page does not save recordings/results
and does not call this application’s backend.

## Documentation

- [Documentation index](docs/00_MASTER_INDEX.md)
- [Project charter and scope](docs/01_PROJECT_CHARTER_AND_SCOPE.md)
- [System architecture](docs/03_SYSTEM_ARCHITECTURE.md)
- [Data model and database](docs/08_DATA_MODELS_AND_DATABASE.md)
- [Tech stack and local deployment](docs/10_TECH_STACK_DEPLOYMENT_AND_CONFIG.md)
- [Architecture decisions and open questions](docs/12_ARCHITECTURE_DECISIONS_AND_OPEN_QUESTIONS.md)
- [Implementation dependency order](docs/13_IMPLEMENTATION_SEQUENCE_AND_DEPENDENCIES.md)
- [Week 1 traceable backlog](assignment/02_Traceable_Backlog_and_Daily_Schedule.md)
