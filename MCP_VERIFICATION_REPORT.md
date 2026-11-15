# TECHOHUB MCP End-to-End Verification

## Final verdict

**PARTIALLY INTEGRATED** — `faq_retrieve` is now reachable through an authenticated customer conversation. The other MCP tools remain unverified in application routing; a single successful FAQ call is not evidence that every exposed tool is integrated.

## Architecture and minimal repair

- `TECHOHUB_MCP_ENABLED` remains opt-in and MCP remains disabled on Vercel. When enabled locally, the workflow creates the stdio MCP client and registers it with `FaqAgent` ([`backend/mcp_client.py`](backend/mcp_client.py#L22-L53), [`backend/workflow.py`](backend/workflow.py#L233-L255)).
- The repair routes only a **single-service `FAQ_SERVICE_POLICY`** query to `agent_faq` when MCP is enabled. Business-hours queries, multi-intent requests, general catalog questions, and multi-service comparisons retain their deterministic paths ([`backend/workflow.py`](backend/workflow.py#L560-L596)).
- `FaqAgent` calls `faq_retrieve` for a connected client and a single-service query. It now consumes the tool's structured answer text and source IDs rather than returning raw JSON ([`backend/agents.py`](backend/agents.py#L323-L350)).
- A unique approved knowledge match now takes precedence over lexical retrieval in the specialist fallback. This prevents a single haircut query from being answered with the combined haircut-and-beard service ([`backend/agents.py`](backend/agents.py#L250-L258)).
- MCP startup transport/protocol failures are normalized to `McpConnectionError` and caught by the workflow so the request continues through the direct path ([`backend/mcp_client.py`](backend/mcp_client.py#L80-L99), [`backend/workflow.py`](backend/workflow.py#L257-L283)).

## Actual end-to-end execution

Ran the actual FastAPI application under Uvicorn with `TECHOHUB_MCP_ENABLED=true`, local runtime, RAG disabled, and a temporary SQLite database. Created an authenticated text session and posted:

> **What is the price and duration of a haircut?**

Evidence:

- Session creation: HTTP 201; authenticated message: HTTP 200.
- LangGraph route: `agent_faq`; specialist: `FaqAgent`.
- Actual MCP tool call: `faq_retrieve` with `{"query":"What is the price and duration of a haircut?"}`.
- MCP result: `is_error=false`, status `answered`, reason `service_catalog`.
- Returned source ID: `fixture:demo-salon-v1:service:haircut`.
- Final assistant response: **“A haircut costs $35 and takes about 30 minutes.”**
- Invocation count: **before repair: 0** across prior authenticated FAQ probes, including a single-service price query; **after repair: 1** for the exact price-and-duration query above.

The result source ID and retrieval reason were also observed at the specialist boundary; the result text and source provenance matched the tool response. The final response did not contain serialized JSON.

## Fallback and deterministic-path verification

Focused authenticated API tests verified:

- **MCP disabled:** the same price-and-duration FAQ returns the approved direct answer; no MCP client is created.
- **MCP unavailable:** pointing the client at a nonexistent server executable caused a real subprocess startup failure. It was normalized and the authenticated request fell back to the approved answer: “A haircut costs $35 and takes about 30 minutes.”
- **Other FAQ paths:** with MCP enabled, “What are your hours?” still uses the deterministic business-hours path; a haircut-and-beard comparison still uses the specialist's direct multi-service path. Neither invokes `call_tool`.
- The unavailable-server regression also guards against returning the combined haircut-and-beard price for a haircut-only query.

No fixtures or existing databases were changed.

## MCP tools and remaining coverage

The MCP server exposes `faq_retrieve`, `service_catalog`, `availability_check`, and `support_info` ([`backend/mcp_server.py`](backend/mcp_server.py#L46-L180)). The application invocation site currently calls only `faq_retrieve`; application routing for the other three tools was not added or verified. In particular, no application conversation was shown to invoke `availability_check` or `support_info`, so this integration is **not fully verified**.

## Validation

- `python -m pytest -q tests/test_mcp.py` — **21 passed**
- `python -m pytest -q tests/test_agents.py tests/test_workflow.py` — **124 passed**
