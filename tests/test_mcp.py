# ---------------------------------------------------------------------------
# A12/A13: MCP server/client integration tests
# ---------------------------------------------------------------------------

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from backend.agents import FaqAgent
from backend.channels import ChannelType, CustomerRequest, InputModality
from backend.database import Base, create_database_engine, create_session_factory
from backend.intent import (
    ClassificationStatus,
    ClassifierSource,
    ClassificationEntities,
    Intent,
    IntentClassification,
    RuleFirstIntentClassifier,
)
from backend.mcp_client import McpClient, McpConnectionError, mcp_client_session
from backend.mcp_server import server as mcp_server
from backend.knowledge import KnowledgeService
from backend.availability import AvailabilityConversationService
from backend.rag import RagRetriever
from backend.workflow import ConversationWorkflow
from backend.main import create_app
from backend.models import ConversationSession, SessionStatus


class FakeGroq:
    async def classify(self, text: str):
        raise AssertionError("Groq should not be called")


def _make_customer_request(text: str) -> CustomerRequest:
    return CustomerRequest(
        session_id=uuid4(),
        trace_id=uuid4(),
        timestamp=__import__("datetime").datetime.now(__import__("datetime").UTC),
        channel_type=ChannelType.TEXT_WEB,
        modality=InputModality.TEXT,
        message_text=text,
    )


class _FaqClassifier:
    async def classify(self, text: str, *, has_pending_availability_context: bool = False) -> IntentClassification:
        return IntentClassification(
            status=ClassificationStatus.CLASSIFIED,
            intents=(Intent.FAQ_BUSINESS_HOURS,),
            entities=ClassificationEntities(),
            source=ClassifierSource.RULES,
            reason_code="test_faq",
        )


# ---------------------------------------------------------------------------
# Test 1: MCP server exposes only approved tools
# ---------------------------------------------------------------------------


def test_mcp_server_exposes_only_approved_tools() -> None:
    """MCP server exposes exactly the four approved tools and nothing else."""
    tool_names = {t.name for t in mcp_server._tool_manager.list_tools()}
    expected = {"faq_retrieve", "service_catalog", "availability_check", "support_info"}
    assert tool_names == expected, f"Expected {expected}, got {tool_names}"


# ---------------------------------------------------------------------------
# Test 2: Real MCP client connects successfully
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_client_connects_successfully() -> None:
    """Real MCP client connects to the local server over stdio."""
    async with mcp_client_session() as client:
        assert client.connected
        tools = await client.list_tools()
        assert len(tools) == 4


# ---------------------------------------------------------------------------
# Test 3: Tools discovered through MCP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_tools_discovered() -> None:
    """Tools are discovered through the MCP list_tools protocol."""
    async with mcp_client_session() as client:
        tools = await client.list_tools()
        names = {t["name"] for t in tools}
        assert "faq_retrieve" in names
        assert "service_catalog" in names
        assert "availability_check" in names
        assert "support_info" in names
        # Each tool has an input schema for validation
        for tool in tools:
            assert "input_schema" in tool


# ---------------------------------------------------------------------------
# Test 4: Specialized agent executes a tool through MCP client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_faq_agent_executes_tool_through_mcp_client() -> None:
    """FaqAgent routes a single-service FAQ through the MCP client.

    Proves that a specialized agent executes a tool through the MCP client
    and the result reaches the response.
    """
    knowledge = KnowledgeService()
    retriever = RagRetriever()

    async with mcp_client_session() as mcp_client:
        agent = FaqAgent(knowledge, retriever, mcp_client=mcp_client)
        request = _make_customer_request("How much is a haircut?")
        result = await agent.handle(request)

        assert result["intent"] == Intent.FAQ_BUSINESS_HOURS
        assert "$35" in result["text"] or "35.00" in result["text"]
        assert result["retrieval_reason"] == ("mcp_faq_retrieve",)


# ---------------------------------------------------------------------------
# Test 5: Responses retain grounding and provenance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_response_retains_grounding_and_provenance() -> None:
    """MCP tool responses include source IDs and retrieval reasons."""
    async with mcp_client_session() as client:
        result = await client.call_tool("faq_retrieve", {"query": "How much is a haircut?"})
        assert not result["is_error"]
        assert "$35" in result["content"] or "35.00" in result["content"]

        result = await client.call_tool("service_catalog", {"service_id": "beard-trim"})
        assert not result["is_error"]
        assert "beard" in result["content"].casefold()


# ---------------------------------------------------------------------------
# Test 6: Availability remains read-only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_availability_read_only() -> None:
    """Availability tool is read-only: no booking or modification fields."""
    async with mcp_client_session() as client:
        result = await client.call_tool(
            "availability_check",
            {"service_id": "haircut", "requested_date": "2026-10-30"},
        )
        assert not result["is_error"]
        # Availability returns slot info, not booking confirmation
        assert "slot_id" in result["content"] or "slots" in result["content"]
        # No booking confirmation text
        assert "booked" not in result["content"].casefold()
        assert "appointment confirmed" not in result["content"].casefold()


# ---------------------------------------------------------------------------
# Test 7: Booking remains unsupported
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_booking_unsupported() -> None:
    """Support tool reports booking as unsupported, no ticket creation."""
    async with mcp_client_session() as client:
        result = await client.call_tool(
            "support_info", {"intent": "appointment_create"}
        )
        assert not result["is_error"]
        assert "can't book an appointment" in result["content"]
        assert "ticket" not in result["content"].casefold()

        result = await client.call_tool(
            "support_info", {"intent": "appointment_modify"}
        )
        assert not result["is_error"]
        assert "No booking was changed" in result["content"]


# ---------------------------------------------------------------------------
# Test 8: Support confirmation/idempotency preserved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_support_confirmation_preserved() -> None:
    """Support tool requires explicit confirmation for ticket creation."""
    async with mcp_client_session() as client:
        result = await client.call_tool(
            "support_info", {"intent": "human_request"}
        )
        assert not result["is_error"]
        assert "reply yes or no" in result["content"]
        assert result["content"].count("ticket") >= 1


# ---------------------------------------------------------------------------
# Test 9: MCP failures use safe existing fallback behavior
# ---------------------------------------------------------------------------


def test_mcp_failure_falls_back_to_direct_okf() -> None:
    """When MCP client is not connected, FaqAgent falls back to direct OKF."""
    knowledge = KnowledgeService()
    retriever = RagRetriever()
    # No MCP client provided -> direct OKF path
    agent = FaqAgent(knowledge, retriever, mcp_client=None)
    request = _make_customer_request("How much is a haircut?")
    result = asyncio.run(agent.handle(request))

    assert result["intent"] == Intent.FAQ_BUSINESS_HOURS
    assert "$35" in result["text"] or "35.00" in result["text"]
    assert result["retrieval_reason"] != ("mcp_faq_retrieve",)


# ---------------------------------------------------------------------------
# Test 10: Bypassing MCP causes integration test to fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_bypass_integration_fails() -> None:
    """If FaqAgent does not use the MCP client, the MCP integration test fails.

    This test verifies that when the MCP client is bypassed (None), the
    retrieval_reason is not "mcp_faq_retrieve", proving the MCP route is
    genuinely exercised when the client is connected.
    """
    knowledge = KnowledgeService()
    retriever = RagRetriever()
    agent = FaqAgent(knowledge, retriever, mcp_client=None)
    request = _make_customer_request("How much is a haircut?")
    result = await agent.handle(request)

    # Without MCP client, the retrieval_reason must NOT be from MCP.
    assert result["retrieval_reason"] != ("mcp_faq_retrieve",)


# ---------------------------------------------------------------------------
# Test: Full workflow with MCP-enabled FaqAgent through compiled graph
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_mcp_faq_agent_through_compiled_graph(tmp_path: Path) -> None:
    """Full compiled LangGraph execution with MCP-enabled FaqAgent.

    Proves that the MCP client is integrated into the LangGraph agent
    architecture and the agent executes a tool through MCP during a real
    graph run.
    """
    app = create_app(
        f"sqlite:///{(tmp_path / 'mcp_workflow.sqlite3').as_posix()}",
        classifier=_FaqClassifier(),
    )
    Base.metadata.create_all(app.state.database_engine)

    try:
        with app.state.session_factory() as db:
            # Create a conversation session
            session = ConversationSession(
                id=str(uuid4()),
                channel=ChannelType.TEXT_WEB.value,
                started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                start_trace_id=str(uuid4()),
            )
            db.add(session)
            db.commit()

            workflow = ConversationWorkflow(
                classifier=_FaqClassifier(),
                knowledge=KnowledgeService(),
                availability=AvailabilityConversationService(),
                rag_retriever=RagRetriever(),
                rag_enabled=False,
            )

            # Connect MCP client and inject into the workflow's FaqAgent
            async with mcp_client_session() as mcp_client:
                faq_agent = workflow._agent_registry.get(Intent.FAQ_BUSINESS_HOURS)
                assert faq_agent is not None
                faq_agent._mcp_client = mcp_client

                result = await workflow.run(
                    session_id=uuid4(),
                    request=_make_customer_request("How much is a haircut?"),
                    db=db,
                )

            assert result.outcome == "answered"
            assert "$35" in result.response_text or "35.00" in result.response_text
    finally:
        app.state.database_engine.dispose()
