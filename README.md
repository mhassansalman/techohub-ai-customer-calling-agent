# TECHOHUB AI Customer Calling Agent

An academic prototype of a transparent, knowledge-grounded customer-service
assistant for a fictional salon. The project is initialized for local Windows
development; application features have not yet been implemented.

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

The customer-facing frontend entrypoint and UI behavior are intentionally
deferred to P12; the compatibility page is a standalone spike only.
Do not commit `.env` files, credentials, local databases, or generated
recordings.

## Backend scaffold

The FastAPI application currently provides only the session lifecycle API
described below. Start it from the repository root after installing the Python
dependencies:

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

Session history can be read by the persistence layer for tests and trusted
application code. A transcript-reading HTTP endpoint is intentionally absent
until staff access control is implemented. The default local SQLite database
is `data/techohub.db`; it is ignored by Git.

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
