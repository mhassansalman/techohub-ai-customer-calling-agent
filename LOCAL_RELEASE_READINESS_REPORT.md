# TECHOHUB Local Release Readiness

Date: 2026-11-14

Scope: local verification of the newer TECHOHUB worktree only. No staging,
branch creation, commit, tag, push, merge, deployment, or older-worktree access
was performed for this release check.

## 1. Git state and baseline

| Item | Result |
| --- | --- |
| Worktree | `F:\hassanS4\TECHOHUB\TECHOHUB_AI_Customer_Calling_Agent-w2` |
| Current branch | `fix/local-recovery-2026-11-14`; no upstream configured |
| HEAD | `893a828aa7df66e38106cf8356724b65c151d2f2` (`fix: declare Vercel Python runtime dependencies`) |
| Remote baseline | HEAD equals `origin/fix/vercel-python-dependencies`; its tree equals `origin/main` (commit `6ce996c462d93009d2407fe5030bcba222d48729`) |
| Worktree | 16 modified tracked files and 9 untracked files before this report; no staged changes |
| Release branches | No `release/*` or `local-release*` branch exists |
| Existing tags | Latest observed: `v0.5.2-architecture-page`; `v0.5.3-local` is unused |
| Diff hygiene | `git diff --check` passed |

No branch, commit, or tag was created. The worktree remains dirty and all
pre-existing changes were preserved.

## 2. Changed files and purpose

The proposed local-release changes are:

| Files | Purpose |
| --- | --- |
| `.env.example`, `.gitignore`, `README.md`, `backend/local.py`, `backend/main.py` | Document and select an explicit local SQLite runtime without changing the hosted database path |
| `backend/agents.py`, `backend/fixtures.py`, `backend/intent.py`, `backend/knowledge.py`, `backend/mcp_client.py`, `backend/rag.py`, `backend/workflow.py` | Deterministic conversation routing, approved-knowledge precedence, scoped follow-ups, date handling, cached semantic retrieval, and the narrow MCP FAQ integration |
| `frontend/src/App.jsx`, `frontend/src/App.test.jsx` | Read the API's `access_token` response field and cover the client behavior |
| `tests/test_local_recovery.py`, `tests/test_mcp.py`, `tests/test_ticket_confirmation.py`, `tests/test_workflow.py` | Regression coverage for local mode, authenticated MCP routing/fallback, conversation behavior, and ticket confirmation |
| `LOCAL_RECOVERY_REPORT.md`, `MCP_VERIFICATION_REPORT.md`, `LOCAL_RELEASE_READINESS_REPORT.md` | Local recovery, MCP, and current release-verification evidence |

The untracked `DEPLOYMENT_REPORT.md` and `LOCAL_AGENT_VERIFICATION_REPORT.md`
are historical reports and are not proposed for staging. `svc_err.txt` and
`svc_out.txt` are untracked logs and are not proposed for staging.

## 3. Test and build results

| Check | Result |
| --- | --- |
| Full backend suite | **457 passed** in 296.15 seconds; exit code 0. Ran with a temporary SQLite database, Groq disabled, and pytest cache provider disabled. |
| Full frontend Vitest suite | **143 passed** |
| Frontend production build | **Passed**; Vite built 18 modules into a unique temporary output directory, which was removed afterward. Existing ignored `frontend/dist` was not used as the output directory. |
| Backend startup/lifespan | **Passed** under Uvicorn; the app started, served requests, and shut down cleanly. |
| `git diff --check` | **Passed** |

The full backend suite includes the focused local-recovery, workflow,
authentication, database-engine, lexical/semantic RAG, ticket, and MCP tests.
The RAG tests cover lexical and cached/offline semantic paths and their
fallback/provenance behavior. The MCP suite covers disabled and unavailable
fallbacks as well as the enabled FAQ path. No unrelated test suite was run.

## 4. Authenticated application smoke

Ran the actual FastAPI app with Uvicorn, real HTTP requests, a temporary SQLite
database, `TECHOHUB_RUNTIME=local`, MCP enabled, RAG disabled, and Groq
credentials absent. The process also had `VERCEL=1` and an unused PostgreSQL
URL set; the local runtime selected SQLite regardless.

| Check | Observed result |
| --- | --- |
| `/health`, `/api/services` | HTTP 200 for both |
| Service catalog | Haircut `$35.00` / 30 minutes; beard trim `$18.00` / 20 minutes; combo `$45.00` / 45 minutes |
| Session lifecycle | Authenticated create (201), read, message, and end succeeded |
| Session authorization | Missing and invalid `X-Session-Token` rejected with 401 for reads, messages, and end; valid token accepted |
| Multi-turn and multi-intent | Haircut price followed by “How long does it take?” returned the contextual 30-minute answer; a combined hours/beard-trim query returned both grounded facts |
| Business hours | Returned weekday 09:00–18:00 UTC, Saturday 10:00–16:00 UTC, Sunday closed |
| Fixture-date limitation | “Any haircut slots tomorrow?” returned no recorded slots for `2026-11-15` and explicitly said this does not establish real-world unavailability |
| Acknowledgment / out of scope | “thank u” received a deterministic acknowledgment; weather query safely requested a rephrase |
| Ticket flow | Explicit yes queued one ticket; a repeated yes created no second ticket; explicit no created none |
| Staff authorization | Missing `X-Staff-API-Key` rejected with 401; the test-only key returned the single queued ticket |
| Temporary data | Ticket count and queue-audit count were each one; temporary database directory was removed |

Voice-related frontend tests use mocked browser APIs. No physical microphone,
live-call, speech-service, or audible-output verification is claimed.

## 5. Architecture and preservation checks

- The local entry point selects SQLite independently of deployment environment
  variables. The smoke confirmed the SQLite engine was selected even with
  `VERCEL=1` and a PostgreSQL-shaped unused URL.
- PostgreSQL/Neon support, TLS/pooling configuration, and deployment runtime
  checks remain in the existing database and hosted configuration paths. Those
  files were not changed; the full database-engine tests passed. No live Neon
  connection was attempted.
- Session-token checks remained enforced in the real HTTP smoke. Staff ticket
  access remained protected by the staff API key.
- No database reset or existing database/fixture modification was performed.
  The application smoke and full suite used temporary test databases.
- The frontend build wrote only to a temporary output directory. Existing
  `frontend/dist`, `frontend/node_modules`, and ignored pytest caches were not
  staged or altered by the build.

## 6. MCP verification

**MCP status: PARTIALLY INTEGRATED.** An authenticated customer FAQ reaches the
real server and uses its result, but not every exposed MCP capability is
integrated into the application.

The MCP-enabled Uvicorn smoke invoked the real stdio server through the
application's original `McpClient.call_tool` implementation. A passive wrapper
counted calls and recorded returned results; it did not substitute a mock
client or tool.

| Query | LangGraph route / specialist | Actual tool and result | Final assistant response |
| --- | --- | --- | --- |
| “What is the price and duration of a haircut?” | `agent_faq` / `FaqAgent` | `faq_retrieve`; `is_error=false`, status `answered`, reason `service_catalog`, source `fixture:demo-salon-v1:service:haircut` | “A haircut costs $35 and takes about 30 minutes.” |
| “How long does it take?” after that question | `agent_faq` / `FaqAgent`, with service context `(Haircut)` | `faq_retrieve`; `is_error=false`, status `answered`, same haircut source ID | “A haircut takes 30 minutes.” |

Invocation evidence: **before the focused repair, 0 calls** across the
authenticated FAQ probes; **after the repair, 1 call** for the initial
single-service FAQ in the earlier focused run; **2 calls** in this release
smoke for the price/duration question and its contextual follow-up. The
multi-intent hours/beard-trim query did not invoke MCP.

The MCP server exposes `faq_retrieve`, `service_catalog`, `availability_check`,
and `support_info`. Application-level invocation of the latter three remains
unverified. MCP-disabled and MCP-server-unavailable fallback tests passed in
the full backend run. See [MCP_VERIFICATION_REPORT.md](MCP_VERIFICATION_REPORT.md)
and the routing/call sites in [backend/workflow.py](backend/workflow.py),
[backend/agents.py](backend/agents.py), and
[backend/mcp_client.py](backend/mcp_client.py).

## 7. Security and diff audit

- `.env` is ignored and not tracked; its contents were not read. No database
  file is tracked. Local database and generated frontend paths are ignored.
- The proposed staging candidates had no matches for common API-key, bearer
  token, or cloud-key patterns. This pattern scan is not a substitute for
  keeping `.env` and logs out of the release.
- The proposed stage list below excludes logs, old reports, databases,
  credentials, caches, `node_modules`, and build output.
- **Unresolved deployment-config diff:** the committed `vercel.json` at HEAD
  contains `"framework": "fastapi"`. The current worktree removes that property
  and also rewrites `functions.backend/main.py.excludeFiles`. This change was
  not part of local verification, and Vercel behavior was not tested. No
  configuration was changed during this audit. `vercel.json` is deliberately
  excluded from the proposed staging list so the release commit retains the
  known HEAD configuration. Do not use `git add -A`; resolve or separately
  review that worktree diff before any later Vercel change.
- No secrets were printed or included in the proposed file list. No
  deployment, authentication, or database configuration was edited as part of
  this release-readiness check.

## 8. Limitations

- MCP application routing is verified only for `faq_retrieve`; the other
  exposed tools are not verified through customer conversations.
- No live calendar, appointment booking, staff transfer, telephony, or physical
  voice-device behavior is claimed. Availability responses reflect recorded
  fixture slots only.
- Groq was disabled during local release verification; deterministic and safe
  fallback behavior was exercised. No live provider request was made.
- No Vercel deployment or live PostgreSQL/Neon connection was tested.
- The current worktree remains uncommitted. The two historical reports and
  logs noted above remain untracked and should not be swept into a commit.

## 9. Proposed Git release preparation

- Release branch for this publication: `release/v0.5.3-local`
- Commit message: `fix: restore secure local conversations and MCP integration`
- Release tag: `v0.5.3-local`

Stage only the following reviewed files; specifically omit `vercel.json`:

```powershell
git switch -c release/v0.5.3-local
git add -- .env.example .gitignore README.md LOCAL_RECOVERY_REPORT.md MCP_VERIFICATION_REPORT.md LOCAL_RELEASE_READINESS_REPORT.md backend/agents.py backend/fixtures.py backend/intent.py backend/knowledge.py backend/local.py backend/main.py backend/mcp_client.py backend/rag.py backend/workflow.py frontend/src/App.jsx frontend/src/App.test.jsx tests/test_local_recovery.py tests/test_mcp.py tests/test_ticket_confirmation.py tests/test_workflow.py
git diff --cached --check
git diff --cached --name-status
git commit -m "fix: restore secure local conversations and MCP integration" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
git tag -a v0.5.3-local -m "TECHOHUB local release v0.5.3"
```

These are recommendations only; none were executed. Do not publish or push
until the staged diff and the separate `vercel.json` worktree change have been
reviewed.

## 10. Final verdict

**READY WITH DOCUMENTED LIMITATIONS** — the local application, backend,
frontend, authentication, ticket flow, deterministic fallbacks, and one real
MCP FAQ route passed verification. Prepare a release only using the explicit
staging list above. The release does not claim complete MCP-tool coverage,
physical voice acceptance, live booking, or Vercel deployment readiness.
