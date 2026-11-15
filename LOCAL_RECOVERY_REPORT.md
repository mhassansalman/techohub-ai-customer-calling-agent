# Local recovery report

Date: 2026-11-14 (Asia/Karachi). Scope: the newer application in this worktree;
no deployment, infrastructure changes, commits, pushes, merges, releases, or tags.

## Git baseline and preservation

| Item | Observed baseline / action |
| --- | --- |
| Current worktree | `F:\hassanS4\TECHOHUB\TECHOHUB_AI_Customer_Calling_Agent-w2` |
| Starting HEAD | `893a828` — `fix: declare Vercel Python runtime dependencies` |
| Starting branch / upstream | `fix/vercel-python-dependencies` / `origin/fix/vercel-python-dependencies`, same commit |
| Recovery branch | `fix/local-recovery-2026-11-14`, created from that HEAD without discarding changes |
| Remote | `origin`: `mhassansalman/techohub-ai-customer-calling-agent`; no fetch/push performed |
| Existing modified files | `.gitignore`, `frontend/src/App.test.jsx`, `vercel.json`; preserved |
| Existing untracked files | `DEPLOYMENT_REPORT.md`, `svc_err.txt`, `svc_out.txt`; preserved |
| Read-only older worktree | `F:\hassanS4\TECHOHUB\TECHOHUB_LAST_WORKING`, detached at `2cd1d78`, reference `v0.5.2-architecture-page` |
| Older worktree status | Existing untracked `OLDER_RELEASE_QA_REPORT.md`; no files written there |
| Git ownership | Sandboxed Git rejected repository ownership; command-scoped safe-directory settings used outside the sandbox, without changing global Git configuration |

The newer release retains the same FastAPI/React/LangGraph/domain-service
architecture. Changes since `2cd1d78` introduced per-session tokens, staff
authentication, CORS restrictions, PostgreSQL/Neon engine support, and
Vercel/Render configuration. The confirmed browser regression came from the
new frontend token wiring. The older UUID-only session access was not restored.

## Local runtime configuration

| Concern | Local behavior |
| --- | --- |
| Start backend | `.\.venv\Scripts\python.exe -m backend.local --reload` |
| Start frontend | From `frontend`: `npm.cmd run dev` |
| Backend address | `http://127.0.0.1:8000`; optional `--port` argument |
| Frontend address | Vite defaults to `http://127.0.0.1:5173` |
| Local mode | Entry point sets `TECHOHUB_RUNTIME=local`; deployment `VERCEL` and `DATABASE_URL` do not select its runtime/database |
| Database | Repository-absolute `data/techohub.db`; override with `TECHOHUB_LOCAL_DATABASE_URL` using SQLite only |
| Deployment preservation | Normal `backend.main:app` keeps existing Vercel PostgreSQL validation, Neon/TLS/pooling support, and all deployment files/dependencies |
| Frontend API | Default `/api`; Vite proxies to `127.0.0.1:8000`; hosted API overrides must include `/api` |
| CORS | Local Vite proxy is same-origin; no wildcard or authentication bypass added |
| Environment files | Existing files/secrets preserved. Groq settings retain root `.env` loading; other backend options use process environment variables |
| Provider credentials | Optional for core conversations; recognized requests resolve deterministically even with a Groq key configured |
| Python installation | Install both `requirements.lock.txt` and `requirements.txt`; the older local lock alone omits newer MCP/PostgreSQL runtime declarations |
| RAG | Off by default; `TECHOHUB_RAG_ENABLED=true`, provider `lexical` or `semantic`; semantic model loading restricted to existing local cache |
| MCP | Optional, off by default; enable with `TECHOHUB_MCP_ENABLED=true`; real local stdio protocol tested |
| Relative dates | Local entry point defaults `TECHOHUB_CLOCK_MODE=system` (salon uses UTC); explicit `fixture` preserves the repeatable October demo |
| Fixture availability | Recorded slots remain on 2026-10-30/31. Current-date searches can correctly return no recorded slots. No slot dates were moved or invented |
| Session ownership | Creation returns `access_token`; subsequent session requests require `X-Session-Token`; cross-session tokens rejected |
| Session persistence | Backend token/state survives restart; frontend token remains in memory and page reload starts a fresh conversation |
| Session expiration | Existing behavior retained: no automatic token TTL; closed sessions reject further messages. Possession of the matching token remains necessary for status reads |

## Confirmed root causes and fixes

| Reproduction before fix | Root cause | Resolution |
| --- | --- | --- |
| Create 201, status/message 401 in browser; 64 frontend tests failed | API returns `access_token`; React read `result.accessToken`, so authenticated headers were empty | Read the actual response field; backend authentication unchanged |
| No-token API reads/messages 401; correct-token reads/messages 200 | Correct access-control behavior, not broken backend token issuance | Preserved and regression-tested |
| Hours + haircut/beard combo returned haircut price $35 instead of $45 | Broad approved FAQ keywords beat named canonical service facts; trimming could split service names containing `and` | Canonical named-service precedence and precise duration-clause trimming |
| Separate haircut/beard price questions abstained | Multiple known services treated as an unknown/ambiguous service before FAQ agent routing | Classify supported FAQ comparisons and resolve each approved service independently |
| Real Chrome lost prices from a compound question while offline tests passed | Configured Groq could override the complete new multi-service rules classification | Keep that supported classification on the deterministic fast path; explicit no-provider-call regression |
| `thank u` / `got it` requested rephrasing | Missing thanks alias; acknowledgment phrases were declared but unused | Deterministic phrase handling; mixed business requests still use capability routing |
| Haircut question → `How long does it take?` could not classify | Only availability selections had explicit follow-up context | Narrow price/duration references use recent customer history in the same session; stored customer text stays original |
| `speak with a human` failed offline classification | Human-request pattern recognized `to` but not `with` | Add `with`; ticket confirmation remains mandatory |
| `tomorrow` returned 2026-10-30 on 2026-11-14 | All relative-date interpretation used the pinned fixture clock | Explicit current-clock local mode; immutable recorded slots preserved |
| Day-specific hours with lexical RAG could return a general weekly paragraph | Generic retrieved text bypassed day-scoped structured facts | Use canonical day-specific hours for those requests |
| Local startup could inherit hosted database/runtime assumptions | Generic entry point uses `DATABASE_URL` and `VERCEL` | Explicit SQLite local entry point; deployment path preserved |

The existing root SQLite schema already contains `access_token`; this was not
a schema-migration failure. No reset or migration was necessary. Existing
database files were inspected read-only; all tests used temporary databases,
and the browser used `.pytest_cache/recovery-browser.sqlite3`.

## Files changed by this recovery

| File(s) | Reason |
| --- | --- |
| `frontend/src/App.jsx` | Correct the token response field |
| `backend/main.py`, new `backend/local.py` | Explicit local SQLite runtime independent of hosted configuration |
| `backend/fixtures.py` | Select system or pinned interpretation clock without editing fixture records |
| `backend/intent.py` | Known multi-service FAQ routing, plural prices, `with` handoff wording, deterministic priority |
| `backend/knowledge.py` | Prefer canonical facts for named services over broad FAQ keyword hits |
| `backend/workflow.py` | Scoped follow-ups, acknowledgments, independent service aggregation, safe answer trimming, day-specific hours |
| `backend/agents.py` | Preserve day-specific hours in FAQ agent lookup |
| `backend/rag.py` | Enforce cached-model-only loading already promised by the provider contract |
| New `tests/test_local_recovery.py` | Offline conversation matrix, provider-priority regression, auth persistence, context isolation, local configuration and date checks |
| `README.md`, `.env.example` | Reproducible local startup and correct API-prefix/configuration examples; no credentials |
| `LOCAL_RECOVERY_REPORT.md` | Results, scope, and limitations |

The user's existing `frontend/src/App.test.jsx` changes were preserved and used
as regression coverage; this recovery did not rewrite that test file.

## Automated verification

| Check | Result |
| --- | --- |
| Full backend suite, final code, Groq disabled, cached semantic model only | **427 passed in 310.06 seconds**; exit code 0; all databases temporary |
| FastAPI lifecycle suite | 24 passed; real TestClient and temporary SQLite |
| Conversation/knowledge/LangGraph/intent/recovery subset | 213 passed; before adding the final explicit provider-priority regression |
| Final intent + recovery subset | 76 passed, including the provider-priority regression |
| Real MCP suite | 17 passed: discovery, read-only domain tools, compiled workflow integration, confirmation and fallback tests |
| RAG suite with network disabled | 49 passed, including actual cached sentence-transformer embeddings, lexical retrieval, and graph integration |
| Frontend baseline | 64 failed, 34 passed; authenticated mocks reproduced missing tokens |
| Frontend after token fix | 98 passed in 2 files, including Message/Mic/Live Call/Call-Only simulated speech flows |
| Frontend production build | Passed; 18 modules, generated Vite production assets |
| Installed Python dependency consistency | `python -m pip check`: no broken requirements found |
| Real Chrome + React + Vite + FastAPI | Passed on final code with the optional configured provider present; asserted actual answer content and service-card rendering |
| SQLite persistence | Token and closed-session state survived app recreation; original customer messages and confirmed ticket persisted |
| Unauthorized access | Missing/wrong/cross-session tokens rejected; closure and mutation authorization remain enforced |
| Final repository check | `git diff --check` passed; HEAD remains `893a828`; original user changes and older-worktree status preserved |

Initial broad runs were interrupted/replaced during diagnosis; they are not
reported as successful full-suite runs. A sandboxed Vitest worker run timed
out; the completed run outside the sandbox passed. Backend suite selection
is `tests`. Evidence logs and the Chrome screenshot are in the ignored
`.pytest_cache` directory. Temporary browser-check services were stopped
after verification so the normal local startup ports are free.

## Actual conversational results

| Input / sequence | Verified response |
| --- | --- |
| Hours + haircut price | Weekly hours plus haircut $35 |
| Hours + beard-trim price | Weekly hours plus beard trim $18 |
| Hours + haircut/beard combo | Weekly hours plus combo $45; not haircut $35 |
| Hours + separate haircut/beard prices | Both $35 and $18 with hours |
| `Are you open Saturday?` | Saturday 10:00–16:00 Etc/UTC |
| Haircut price → `How long does it take?` | Haircut price $35, then 30 minutes |
| `thanks`, `thank u`, `got it` | Deterministic acknowledgment; no model dependency |
| Friday slots → Saturday correction in pinned demo mode | Only recorded 2026-10-30/31 slots; fixture disclaimer; context persisted |
| `Any haircut slots tomorrow?` in current local mode on Nov 14 | No recorded fixture slots for 2026-11-15; no claim of real-world unavailability |
| Browse services in Chrome | Three rendered cards: $35/30 min, $18/20 min, $45/45 min |
| Human-support request → yes | Confirmation prompt followed by a persisted queued ticket ID |
| Human-support request → no | No ticket created |
| API-key request | Refuses to share credentials |
| Out-of-scope question | Safe request to rephrase; no fabricated business answer |
| End conversation | Closed state displayed and persisted; later writes rejected |

Chrome verification used a real browser and real HTTP application stack.
Speech-recognition/synthesis assertions in Vitest use mocked browser APIs;
they do not prove microphone permission, recognition-service connectivity,
audible output, or a successful physical-device conversation.

## Remaining limitations and comparison

| Area | Status |
| --- | --- |
| Message Mode / authenticated local chat | Restored and verified in real Chrome |
| Mic, Live Call, Call-Only | Existing features retained; automated flows pass. Actual microphone/device/browser-service acceptance remains unverified |
| General natural-language context | Supported narrow service price/duration references and existing availability corrections; unrestricted pronoun/topic resolution is not implemented |
| Booking / live staff transfer / telephony | Existing prototype limitations retained; queued tickets are not a live transfer, and no real bookings occur |
| Fixture freshness | Explicit historical fixture dates preserved; current relative-date interpretation no longer implies those are current slots |
| Optional semantic model | Installed cached model worked here; without the optional model, deterministic/lexical paths remain available |
| Older-release session implementation | Not copied; newer token ownership checks retained |
| Older pricing/context/acknowledgment defects | Reproduced applicable cases in the newer code and fixed; plain `thanks` already worked |
| Older offline handoff concern | Existing `human support` worked; additional `speak with a human` gap reproduced and fixed |
| Existing data | Root database, old database, canonical fixture, and older worktree preserved |

Preserved file SHA-256 values (read-only checks):

| File | SHA-256 |
| --- | --- |
| `data/techohub.db` | `2E98DB9812EAE8C70E677408DFE9A7316D48ACD3CD2EF6716244820A9E75A682` |
| `data/techohub.db.old` | `A31AB8C40D4110918513C8225A4671A09EDA00E5B01158190D009B895F8E7D3A` |
| `fixtures/demo_salon.json` | `4E76FCAEEC1D0070AF6F285B68B3CCDEEFFEF56CB1FC879F042B5FF41CABCD89` |

## Local release readiness

**PARTIALLY WORKING** against the complete all-modes acceptance target:
secure local text conversations are restored and browser-verified; physical
microphone/live-call/Call-Only acceptance is still outstanding. Automated voice
tests pass, but are not substituted for actual device verification. No
deployment stage should be inferred from this report. Changes remain
uncommitted for review.
