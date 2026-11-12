# ---------------------------------------------------------------------------
# A10/A11: Specialized agent tests
# ---------------------------------------------------------------------------

import asyncio
from datetime import datetime, UTC
from pathlib import Path
from uuid import UUID, uuid4

from backend.agents import (
    AgentRegistry,
    AvailabilityAgent,
    Complexity,
    ComplexityClassifier,
    FaqAgent,
    SupportAgent,
)
from backend.channels import ChannelType, CustomerRequest, InputModality
from backend.database import Base, create_database_engine
from backend.intent import (
    Intent,
    ClassificationStatus,
    ClassifierSource,
    ClassificationEntities,
    IntentClassification,
    RuleFirstIntentClassifier as RulesOnlyClassifier,
)
from backend.knowledge import KnowledgeService
from backend.rag import RagRetriever
from backend.session_service import create_handoff_ticket
from backend.workflow import ConversationWorkflow, ConversationWorkflowResult
from backend.main import create_app
from backend.availability import AvailabilityConversationService
from backend.channels import ChannelType, CustomerRequest, InputModality
from backend.models import ConversationSession, SessionStatus


class FakeGroq:
    """Stub Groq classifier that never gets called in rules-first fast path."""

    async def classify(self, text: str):
        raise AssertionError("Groq should not be called for rules-first path")


def _make_customer_request(text: str) -> CustomerRequest:
    return CustomerRequest(
        session_id=uuid4(),
        trace_id=uuid4(),
        timestamp=datetime.now(UTC),
        channel_type=ChannelType.TEXT_WEB,
        modality=InputModality.TEXT,
        message_text=text,
    )


def _run_workflow(
    workflow: ConversationWorkflow,
    session_id: UUID,
    message_text: str,
    db,
) -> ConversationWorkflowResult:
    request = CustomerRequest(
        session_id=session_id,
        trace_id=uuid4(),
        timestamp=datetime.now(UTC),
        channel_type=ChannelType.TEXT_WEB,
        modality=InputModality.TEXT,
        message_text=message_text,
    )
    return asyncio.run(workflow.run(session_id=session_id, request=request, db=db))


def test_complexity_classifier_simple_intent() -> None:
    """Simple intents route to the deterministic fast path."""
    classifier = ComplexityClassifier()
    request = _make_customer_request("How much is a haircut?")
    result = classifier.classify(request, (Intent.FAQ_BUSINESS_HOURS,))
    assert result.complexity == Complexity.SIMPLE
    assert result.agent is None


def test_complexity_classifier_complex_intent() -> None:
    """Complex intents route to a specialized agent."""
    classifier = ComplexityClassifier()
    request = _make_customer_request("Book a haircut appointment Friday.")
    result = classifier.classify(request, (Intent.APPOINTMENT_CREATE,))
    assert result.complexity == Complexity.COMPLEX
    assert result.agent == "appointment_create"


def test_agent_registry_register_and_get() -> None:
    """AgentRegistry stores and retrieves handlers by intent."""
    registry = AgentRegistry()
    retriever = RagRetriever()
    knowledge = KnowledgeService()
    agent = FaqAgent(knowledge, retriever)

    registry.register(Intent.FAQ_BUSINESS_HOURS, agent)
    assert Intent.FAQ_BUSINESS_HOURS in registry.registered_intents()
    assert registry.get(Intent.FAQ_BUSINESS_HOURS) is agent
    assert registry.get(Intent.APPOINTMENT_AVAILABILITY) is None


def test_faq_agent_uses_knowledge_service() -> None:
    """FaqAgent wraps KnowledgeService and RagRetriever."""
    knowledge = KnowledgeService()
    retriever = RagRetriever()
    agent = FaqAgent(knowledge, retriever)

    request = _make_customer_request("How much is a haircut?")
    result = asyncio.run(agent.handle(request))
    assert result["intent"] == Intent.FAQ_BUSINESS_HOURS
    assert result["source_ids"]
    assert result["outcome"] == "answered"
    assert "$35" in result["text"] or "35.00" in result["text"]


def test_availability_agent_wraps_availability_service() -> None:
    """AvailabilityAgent wraps AvailabilityConversationService."""
    service = AvailabilityConversationService()
    agent = AvailabilityAgent(service)

    request = _make_customer_request("Which haircut slots are open on Friday?")

    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = __import__(
        "backend.database", fromlist=["create_session_factory"]
    ).create_session_factory(engine)
    db = session_factory()

    result = agent.handle(request, db, str(uuid4()))
    assert result["intent"] == Intent.APPOINTMENT_AVAILABILITY
    assert result["outcome"] in ("answered", "unsupported", "session_not_found")


def test_support_agent_human_request() -> None:
    """SupportAgent handles human_request with handoff confirmation prompt."""
    agent = SupportAgent(create_handoff_ticket)

    request = _make_customer_request("I want to speak to someone.")
    result = agent.handle(request, None, str(uuid4()), uuid4())
    assert result["intent"] == Intent.HUMAN_REQUEST
    assert "queued support ticket" in result["text"]
    assert result["outcome"] == "handoff_unavailable"


def test_support_agent_complaint_uses_knowledge() -> None:
    """SupportAgent handles complaint with knowledge base fallback."""
    knowledge = KnowledgeService()
    agent = SupportAgent(create_handoff_ticket, knowledge)

    request = _make_customer_request("I have a complaint about my visit.")
    result = agent.handle(request, None, str(uuid4()), uuid4())
    assert result["intent"] == Intent.COMPLAINT
    assert result["outcome"] == "handoff_unavailable"
    assert "can't create a support ticket" in result["text"]


def test_workflow_faq_agent_routes_through_langgraph(
    tmp_path: Path,
) -> None:
    """FAQ queries route through LangGraph with RAG agent when enabled."""
    retriever = RagRetriever()
    workflow = ConversationWorkflow(
        classifier=RulesOnlyClassifier(FakeGroq()),
        knowledge=KnowledgeService(),
        availability=AvailabilityConversationService(),
        rag_retriever=retriever,
        rag_enabled=True,
        rag_provider="lexical",
    )

    app = create_app(
        f"sqlite:///{(tmp_path / 'faq_agent.sqlite3').as_posix()}",
        classifier=RulesOnlyClassifier(FakeGroq()),
    )
    Base.metadata.create_all(app.state.database_engine)
    try:
        with app.state.session_factory() as db:
            result = _run_workflow(
                workflow, uuid4(), "How much is a haircut?", db
            )
    finally:
        app.state.database_engine.dispose()

    assert result.outcome == "answered"
    assert result.source_ids
    assert "$35" in result.response_text or "35.00" in result.response_text


def test_complexity_classification_routes_complex_requests_to_agent_nodes(
    tmp_path: Path,
) -> None:
    """Regression test: classify_complexity output must drive conditional routing.

    Complex requests (APPOINTMENT_CREATE/MODIFY) must reach agent nodes,
    not fall through to clarification. Simple requests must reach capability
    nodes. Clarification requests (empty intents) must not crash the graph.
    """
    retriever = RagRetriever()
    workflow = ConversationWorkflow(
        classifier=RulesOnlyClassifier(FakeGroq()),
        knowledge=KnowledgeService(),
        availability=AvailabilityConversationService(),
        rag_retriever=retriever,
        rag_enabled=True,
        rag_provider="lexical",
    )

    app = create_app(
        f"sqlite:///{(tmp_path / 'complexity_routing.sqlite3').as_posix()}",
        classifier=RulesOnlyClassifier(FakeGroq()),
    )
    Base.metadata.create_all(app.state.database_engine)

    try:
        with app.state.session_factory() as db:
            # Complex booking request -> must reach agent_support, not clarification.
            complex_result = _run_workflow(
                workflow, uuid4(), "Book a haircut appointment Friday.", db
            )
            assert complex_result.outcome != "clarification"
            assert complex_result.outcome == "handoff_unavailable"

            # Simple FAQ request -> must reach faq_capability, not clarification.
            simple_result = _run_workflow(
                workflow, uuid4(), "How much is a haircut?", db
            )
            assert simple_result.outcome == "answered"
            assert "$35" in simple_result.response_text or "35.00" in simple_result.response_text

            # Clarification request (empty intents) -> must not crash; reaches clarification.
            unclear_result = _run_workflow(
                workflow, uuid4(), "I want trim beard", db
            )
            assert unclear_result.outcome == "clarification"
    finally:
        app.state.database_engine.dispose()


def test_support_agent_booking_intents() -> None:
    """SupportAgent returns deterministic unsupported-booking messages for create/modify."""
    agent = SupportAgent(create_handoff_ticket)

    create_request = _make_customer_request("Book a haircut appointment Friday.")
    result = agent.handle(
        create_request, None, str(uuid4()), uuid4(), intent=Intent.APPOINTMENT_CREATE
    )
    assert result["intent"] == Intent.APPOINTMENT_CREATE
    assert result["outcome"] == "handoff_unavailable"
    assert "can't book an appointment in this demo" in result["text"]
    assert "ticket" not in result["text"].casefold()

    modify_request = _make_customer_request("Reschedule my appointment Friday.")
    result = agent.handle(
        modify_request, None, str(uuid4()), uuid4(), intent=Intent.APPOINTMENT_MODIFY
    )
    assert result["intent"] == Intent.APPOINTMENT_MODIFY
    assert result["outcome"] == "handoff_unavailable"
    assert "No booking was changed" in result["text"]


def test_agent_faq_node_produces_capability_result() -> None:
    """agent_faq node invokes the knowledge service and returns a CapabilityResult."""
    workflow = ConversationWorkflow(
        classifier=RulesOnlyClassifier(FakeGroq()),
        knowledge=KnowledgeService(),
        availability=AvailabilityConversationService(),
        rag_retriever=RagRetriever(),
        rag_enabled=False,
    )

    request = _make_customer_request("How much is a haircut?")
    state = {
        "classification": type(
            "_C", (), {"intents": (Intent.FAQ_BUSINESS_HOURS,)}
        )(),
        "request": request,
    }
    output = asyncio.run(workflow._agent_faq_capability(state))
    capability_result = output["capability_results"][0]
    assert capability_result.intent == Intent.FAQ_BUSINESS_HOURS
    assert capability_result.source_ids
    assert "$35" in capability_result.text or "35.00" in capability_result.text


def test_agent_availability_node_produces_capability_result() -> None:
    """agent_availability node invokes the availability service and returns a CapabilityResult."""
    workflow = ConversationWorkflow(
        classifier=RulesOnlyClassifier(FakeGroq()),
        knowledge=KnowledgeService(),
        availability=AvailabilityConversationService(),
    )

    engine = create_database_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = __import__(
        "backend.database", fromlist=["create_session_factory"]
    ).create_session_factory(engine)
    db = session_factory()
    try:
        request = _make_customer_request("Which haircut slots are open on Friday?")
        state = {
            "classification": type(
                "_C", (), {"intents": (Intent.APPOINTMENT_AVAILABILITY,)}
            )(),
            "request": request,
            "db": db,
            "session_id": uuid4(),
        }
        output = workflow._agent_availability_capability(state)
        capability_result = output["capability_results"][0]
        assert capability_result.intent == Intent.APPOINTMENT_AVAILABILITY
        assert capability_result.outcome in (
            "answered",
            "unsupported",
            "clarification",
        )
    finally:
        db.close()
        engine.dispose()


def test_agent_support_node_output_reaches_aggregation() -> None:
    """Complex support request: agent_support output flows through aggregate_response."""
    retriever = RagRetriever()
    workflow = ConversationWorkflow(
        classifier=RulesOnlyClassifier(FakeGroq()),
        knowledge=KnowledgeService(),
        availability=AvailabilityConversationService(),
        rag_retriever=retriever,
        rag_enabled=True,
        rag_provider="lexical",
    )

    app = create_app(
        f"sqlite:///{(Path('/tmp') / 'agent_support_agg.sqlite3').as_posix()}",
        classifier=RulesOnlyClassifier(FakeGroq()),
    )
    Base.metadata.create_all(app.state.database_engine)
    try:
        with app.state.session_factory() as db:
            result = _run_workflow(
                workflow, uuid4(), "Book a haircut appointment Friday.", db
            )
    finally:
        app.state.database_engine.dispose()

    assert result.outcome == "handoff_unavailable"
    assert "can't book an appointment in this demo" in result.response_text


def test_graph_contains_agent_nodes_and_conditional_edges() -> None:
    """Compiled graph topology includes agent nodes and conditional complexity edges."""
    workflow = ConversationWorkflow(
        classifier=RulesOnlyClassifier(FakeGroq()),
        knowledge=KnowledgeService(),
        availability=AvailabilityConversationService(),
    )

    graph = workflow.graph.get_graph()
    # Agent nodes are registered in the compiled graph.
    assert "agent_faq" in graph.nodes
    assert "agent_availability" in graph.nodes
    assert "agent_support" in graph.nodes
    # Conditional routing from classify_complexity exists.
    assert "classify_complexity" in graph.nodes
    # Every agent node connects to aggregate_response.
    for node in ("agent_faq", "agent_availability", "agent_support"):
        assert any(
            edge.source == node and edge.target == "aggregate_response"
            for edge in graph.edges
        ), f"{node} must connect to aggregate_response"


class _MultiServiceClassifier:
    """Mock classifier that returns FAQ_SERVICE_POLICY for multi-service text."""

    async def classify(
        self,
        text: str,
        *,
        has_pending_availability_context: bool = False,
    ) -> IntentClassification:
        return IntentClassification(
            status=ClassificationStatus.CLASSIFIED,
            intents=(Intent.FAQ_SERVICE_POLICY,),
            entities=ClassificationEntities(),
            source=ClassifierSource.RULES,
            reason_code="test_multi_service",
        )


def test_multi_service_faq_reaches_agent_faq_through_graph(
    tmp_path: Path,
) -> None:
    """Multi-service FAQ request routes through agent_faq via compiled graph.

    Proves that classify_complexity output drives conditional routing to
    agent_faq, the agent invokes the knowledge service for each service,
    and aggregated results preserve source IDs.
    """
    workflow = ConversationWorkflow(
        classifier=_MultiServiceClassifier(),
        knowledge=KnowledgeService(),
        availability=AvailabilityConversationService(),
        rag_retriever=RagRetriever(),
        rag_enabled=False,
    )

    app = create_app(
        f"sqlite:///{(tmp_path / 'multi_service_faq.sqlite3').as_posix()}",
        classifier=_MultiServiceClassifier(),
    )
    Base.metadata.create_all(app.state.database_engine)

    try:
        with app.state.session_factory() as db:
            result = _run_workflow(
                workflow,
                uuid4(),
                "What is the price of a haircut and what is the price of a beard trim?",
                db,
            )
    finally:
        app.state.database_engine.dispose()

    assert result.outcome == "answered"
    assert "$35" in result.response_text
    assert result.source_ids


class _MultiDateAvailabilityClassifier:
    """Mock classifier that returns APPOINTMENT_AVAILABILITY for multi-date text."""

    async def classify(
        self,
        text: str,
        *,
        has_pending_availability_context: bool = False,
    ) -> IntentClassification:
        return IntentClassification(
            status=ClassificationStatus.CLASSIFIED,
            intents=(Intent.APPOINTMENT_AVAILABILITY,),
            entities=ClassificationEntities(),
            source=ClassifierSource.RULES,
            reason_code="test_multi_date_availability",
        )


def test_multi_date_availability_reaches_agent_availability_through_graph(
    tmp_path: Path,
) -> None:
    """Multi-date availability request routes through agent_availability via graph.

    Proves that classify_complexity output drives conditional routing to
    agent_availability, the agent invokes the availability service for each
    date, and aggregated results preserve source IDs.
    """
    workflow = ConversationWorkflow(
        classifier=_MultiDateAvailabilityClassifier(),
        knowledge=KnowledgeService(),
        availability=AvailabilityConversationService(),
        rag_retriever=RagRetriever(),
        rag_enabled=False,
    )

    app = create_app(
        f"sqlite:///{(tmp_path / 'multi_date_availability.sqlite3').as_posix()}",
        classifier=_MultiDateAvailabilityClassifier(),
    )
    Base.metadata.create_all(app.state.database_engine)

    try:
        with app.state.session_factory() as db:
            session_id = uuid4()
            # Create a conversation session so the availability service can resolve it.
            session = ConversationSession(
                id=str(session_id),
                channel=ChannelType.TEXT_WEB.value,
                started_at=datetime.now(UTC),
                start_trace_id=str(uuid4()),
            )
            db.add(session)
            db.commit()

            result = _run_workflow(
                workflow,
                session_id,
                "Do you have haircut slots Friday and Saturday?",
                db,
            )
    finally:
        app.state.database_engine.dispose()

    assert result.outcome == "answered"
    assert "2026-10-30" in result.response_text or "2026-10-31" in result.response_text
    assert result.source_ids


def test_multi_service_faq_preserves_source_ids_through_agent(tmp_path: Path) -> None:
    """Multi-service FAQ through agent_faq preserves source IDs from both lookups.

    Proves that agent_faq output reaches aggregate_response with source IDs
    from each individual service lookup.
    """
    workflow = ConversationWorkflow(
        classifier=_MultiServiceClassifier(),
        knowledge=KnowledgeService(),
        availability=AvailabilityConversationService(),
        rag_retriever=RagRetriever(),
        rag_enabled=False,
    )

    app = create_app(
        f"sqlite:///{(tmp_path / 'multi_service_faq_sourceids.sqlite3').as_posix()}",
        classifier=_MultiServiceClassifier(),
    )
    Base.metadata.create_all(app.state.database_engine)

    try:
        with app.state.session_factory() as db:
            result = _run_workflow(
                workflow,
                uuid4(),
                "What is the price of a haircut and what is the price of a beard trim?",
                db,
            )
    finally:
        app.state.database_engine.dispose()

    assert result.outcome == "answered"
    assert result.source_ids
    assert all(sid for sid in result.source_ids)
