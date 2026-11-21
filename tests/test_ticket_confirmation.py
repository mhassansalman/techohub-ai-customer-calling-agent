"""Ticket consent regressions through authenticated HTTP and persistent SQLite."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from backend.main import WORKFLOW_FAILURE_RESPONSE, create_app
from backend.models import AuditEvent, HandoffTicket, Message
from backend.workflow import (
    HANDOFF_ACKNOWLEDGMENT,
    HANDOFF_CLARIFICATION_PROMPT,
    HANDOFF_CONFIRMATION_PROMPT,
    HANDOFF_CONFLICT_PROMPT,
    HANDOFF_PENDING_ACKNOWLEDGMENT_PROMPT,
)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('GROQ_API_KEY', '')
    monkeypatch.setenv('TECHOHUB_MCP_ENABLED', 'false')
    monkeypatch.setenv('TECHOHUB_RAG_ENABLED', 'false')
    return create_app(f"sqlite:///{(tmp_path / 'tickets.db').as_posix()}")


def start(client):
    response = client.post('/api/sessions', json={'channel_type': 'text_web'})
    assert response.status_code == 201
    body = response.json()
    return body['session']['session_id'], {'X-Session-Token': body['access_token']}


def send(client, sid, headers, text):
    response = client.post(f'/api/sessions/{sid}/messages', headers=headers, json={
        'session_id': sid, 'trace_id': str(uuid4()),
        'timestamp': datetime.now(UTC).isoformat(), 'channel_type': 'text_web',
        'modality': 'text', 'message_text': text,
    })
    assert response.status_code == 200, response.text
    return response.json()['assistant_message']['text']


def tickets(app, sid):
    with app.state.session_factory() as db:
        return list(db.scalars(select(HandoffTicket).where(HandoffTicket.session_id == sid)))


@pytest.mark.parametrize('answer', [
    'yes create a ticket', 'create my ticket', 'Yes, create a ticket.',
    'please create my support ticket', 'yes please create a support ticket',
    'queue the ticket', 'yes', 'yep', 'yeah', 'sure', 'please do', 'go ahead',
    'okay',
])
def test_clear_consent_queues_one_ticket_and_duplicate_does_not(app, answer):
    with TestClient(app) as client:
        sid, headers = start(client)
        assert send(client, sid, headers, 'I want to talk to a human') == HANDOFF_CONFIRMATION_PROMPT
        assert tickets(app, sid) == []
        response = send(client, sid, headers, answer)
        queued = tickets(app, sid)
        assert len(queued) == 1
        assert queued[0].id in response and 'has been queued' in response
        send(client, sid, headers, answer)
        send(client, sid, headers, 'yes')
        assert [ticket.id for ticket in tickets(app, sid)] == [queued[0].id]
        with app.state.session_factory() as db:
            audit = list(db.scalars(select(AuditEvent).where(
                AuditEvent.session_id == sid, AuditEvent.action == 'handoff_ticket.queued',
            )))
            assert len(audit) == 1 and audit[0].resource_id == queued[0].id


@pytest.mark.parametrize('answer', [
    'no', 'nope', 'cancel', 'cancel my ticket', 'no do not create a ticket',
    "don't create a ticket", "don't create my support ticket", 'no thanks',
    'No, cancel the request',
])
def test_clear_negative_cancels_pending_operation(app, answer):
    with TestClient(app) as client:
        sid, headers = start(client)
        send(client, sid, headers, 'I want to talk to a human')
        assert "won't create a support ticket" in send(client, sid, headers, answer)
        send(client, sid, headers, 'yes')
        assert tickets(app, sid) == []


@pytest.mark.parametrize('answer', [
    'maybe', 'yes no', 'yes create a ticket but no',
    'I said yes to my friend', 'yes how much is a haircut', 'not sure',
    "don't do it",
])
def test_ambiguous_or_unrelated_affirmation_never_creates_ticket(app, answer):
    with TestClient(app) as client:
        sid, headers = start(client)
        send(client, sid, headers, 'I want to talk to a human')
        response = send(client, sid, headers, answer)
        assert response in {HANDOFF_CLARIFICATION_PROMPT, HANDOFF_CONFLICT_PROMPT}
        assert tickets(app, sid) == []
        assert 'has been queued' in send(client, sid, headers, 'yes create a ticket')
        assert len(tickets(app, sid)) == 1


@pytest.mark.parametrize(
    'answer',
    ['thank', 'thanks', 'thank you', 'thank u', 'appreciate it'],
)
def test_short_thanks_phrases_receive_a_natural_acknowledgment(app, answer):
    with TestClient(app) as client:
        sid, headers = start(client)
        assert send(client, sid, headers, answer) == HANDOFF_ACKNOWLEDGMENT
        assert tickets(app, sid) == []


def test_thanks_during_pending_confirmation_acknowledges_and_preserves_context(app):
    with TestClient(app) as client:
        sid, headers = start(client)
        send(client, sid, headers, 'I want to talk to a human')

        assert send(client, sid, headers, 'thank') == (
            HANDOFF_PENDING_ACKNOWLEDGMENT_PROMPT
        )
        assert tickets(app, sid) == []
        assert 'has been queued' in send(
            client,
            sid,
            headers,
            'yes, create a ticket',
        )
        assert len(tickets(app, sid)) == 1


@pytest.mark.parametrize('answer', ['yes', 'yep', 'yes, create a ticket'])
def test_confirmation_outside_pending_context_never_creates_ticket(app, answer):
    with TestClient(app) as client:
        sid, headers = start(client)
        response = send(client, sid, headers, answer)

        assert 'has been queued' not in response
        assert tickets(app, sid) == []


@pytest.mark.parametrize('new_request, expected', [
    ('I want a haircut on Thursday', '$35'),
    ('What are your hours?', '09:00'),
    ('Any haircut slots on Friday?', 'fixture'),
])
def test_new_topic_exits_pending_operation_even_across_restart(app, new_request, expected):
    with TestClient(app) as client:
        sid, headers = start(client)
        send(client, sid, headers, 'I want to talk to a human')
        assert expected in send(client, sid, headers, new_request)
        assert tickets(app, sid) == []
    restarted = create_app(str(app.state.database_engine.url))
    with TestClient(restarted) as client:
        send(client, sid, headers, 'yes')
        assert tickets(restarted, sid) == []


def test_pending_confirmation_survives_restart_and_checks_auth(app, monkeypatch):
    monkeypatch.setenv('STAFF_API_KEY', 'test-only-staff-key')
    with TestClient(app) as client:
        sid, headers = start(client)
        send(client, sid, headers, 'I want to talk to a human')
    restarted = create_app(str(app.state.database_engine.url))
    with TestClient(restarted) as client:
        denied = client.post(f'/api/sessions/{sid}/messages', json={
            'session_id': sid, 'trace_id': str(uuid4()),
            'timestamp': datetime.now(UTC).isoformat(), 'channel_type': 'text_web',
            'modality': 'text', 'message_text': 'yes',
        })
        assert denied.status_code == 401
        assert tickets(restarted, sid) == []
        assert 'has been queued' in send(client, sid, headers, 'create my ticket')
        assert client.get('/api/staff/tickets').status_code == 401
        staff = client.get('/api/staff/tickets', headers={'X-Staff-API-Key': 'test-only-staff-key'})
        assert staff.status_code == 200 and len(staff.json()) == 1
        assert staff.json()[0]['session_id'] == sid


def test_failed_ticket_insert_is_rolled_back_and_never_reports_success(app):
    def fail_ticket_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO handoff_tickets'):
            raise RuntimeError('test-only simulated storage failure')

    with TestClient(app) as client:
        sid, headers = start(client)
        send(client, sid, headers, 'I want to talk to a human')
        event.listen(app.state.database_engine, 'before_cursor_execute', fail_ticket_insert)
        try:
            answer = send(client, sid, headers, 'yes create a ticket')
        finally:
            event.remove(app.state.database_engine, 'before_cursor_execute', fail_ticket_insert)
        assert answer == WORKFLOW_FAILURE_RESPONSE
        assert tickets(app, sid) == []
        with app.state.session_factory() as db:
            assert db.scalar(select(AuditEvent).where(
                AuditEvent.session_id == sid, AuditEvent.action == 'handoff_ticket.queued',
            )) is None
            assert db.scalar(select(Message).where(
                Message.session_id == sid, Message.text == answer,
            )) is not None


def test_requested_sequence_keeps_ticket_count_at_one(app):
    with TestClient(app) as client:
        sid, headers = start(client)
        answers = [send(client, sid, headers, text) for text in [
            'I want to talk to a human', 'yes create a ticket',
            'create my ticket', 'yes', 'no', 'I want a haircut on Thursday',
        ]]
        assert 'has been queued' in answers[1]
        assert all('has been queued' not in answer for answer in answers[2:])
        assert '$35' in answers[-1]
        assert len(tickets(app, sid)) == 1
