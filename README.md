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

The frontend entrypoint and UI behavior are intentionally deferred to P12.
Do not commit `.env` files, credentials, local databases, or generated
recordings.

## Documentation

- [Documentation index](docs/00_MASTER_INDEX.md)
- [Project charter and scope](docs/01_PROJECT_CHARTER_AND_SCOPE.md)
- [System architecture](docs/03_SYSTEM_ARCHITECTURE.md)
- [Data model and database](docs/08_DATA_MODELS_AND_DATABASE.md)
- [Tech stack and local deployment](docs/10_TECH_STACK_DEPLOYMENT_AND_CONFIG.md)
- [Architecture decisions and open questions](docs/12_ARCHITECTURE_DECISIONS_AND_OPEN_QUESTIONS.md)
- [Implementation dependency order](docs/13_IMPLEMENTATION_SEQUENCE_AND_DEPENDENCIES.md)
- [Week 1 traceable backlog](assignment/02_Traceable_Backlog_and_Daily_Schedule.md)
