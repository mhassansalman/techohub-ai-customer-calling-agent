# TECHOHUB — Verified Local Startup

**Status:** Manually verified working on November 21, 2026.

**Project:** AI Customer Calling Agent

## Prerequisites

- Open the W2 project in VS Code.
- Use Git Bash terminals.
- Existing Python `.venv` and frontend `node_modules` must be available.
- Run backend and frontend in separate terminals.

## Terminal 1 — Backend

```bash
cd /f/hassanS4/TECHOHUB/TECHOHUB_AI_Customer_Calling_Agent-w2

source .venv/Scripts/activate

export TECHOHUB_RUNTIME=local
export TECHOHUB_LOCAL_DATABASE_URL="sqlite:///$(pwd)/data/voice_manual_test.db"
export TECHOHUB_RAG_ENABLED=false
export TECHOHUB_MCP_ENABLED=false

python -m backend.local --port 8000
```

Expected backend URL:

`http://127.0.0.1:8000`

## Terminal 2 — Frontend

```bash
cd /f/hassanS4/TECHOHUB/TECHOHUB_AI_Customer_Calling_Agent-w2/frontend

unset VITE_API_BASE_URL

npm run dev
```

Open the URL Vite displays, normally:

`http://127.0.0.1:5173`

## Important Rules

1. **Use `python -m backend.local` for local startup.**
2. Keep `VITE_API_BASE_URL` unset to use the configured Vite proxy.
3. Do not randomly change database or CORS configuration.
4. Keep both terminals running.
5. Stop both servers using `Ctrl+C`.
6. Use a separate test database instead of modifying `data/techohub.db`.
7. If Vite selects a different frontend port, verify backend CORS configuration before testing.

## Quick Verification

1. Open the frontend.
2. Select Multimodal Assistant.
3. Start a conversation.
4. Ask: "How much is a haircut?"
5. Expected: "A haircut costs $35."
6. Test Mic Mode and support-ticket confirmation separately.

## If It Stops Working

Check in this order:

- Backend is running on port 8000.
- Frontend is using the intended local URL.
- `VITE_API_BASE_URL` is unset.
- Both frontend and backend processes were restarted after configuration changes.
- Browser DevTools Network tab shows whether requests failed because of CORS, authentication, or backend errors.

**Do not reset databases, disable authentication, or change dependencies as an initial troubleshooting step.**
