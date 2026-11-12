"""A12: Local MCP server exposing approved domain tools over stdio.

The server wraps existing TechoHub domain services (KnowledgeService,
AvailabilityService) and exposes only approved, read-only tools. No booking
writes, no arbitrary database/file access, no unrestricted staff operations.
All responses preserve provenance (source IDs) and safe abstention.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.stdio import stdio_server

from backend.availability import AvailabilityService
from backend.knowledge import KnowledgeService


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

server = MCPServer(
    name="techohub-domain-tools",
    title="TechoHub Domain Tools",
    instructions=(
        "Approved read-only tools for the TechoHub AI Customer Calling Agent. "
        "Provides FAQ/knowledge retrieval, service catalog lookup, recorded "
        "synthetic availability checks, and support information. No booking, "
        "no appointment modification, no arbitrary database or file access."
    ),
    version="0.3.0",
)


# ---------------------------------------------------------------------------
# Tool: FAQ / knowledge retrieval
# ---------------------------------------------------------------------------

knowledge = KnowledgeService()


@server.tool(
    name="faq_retrieve",
    description=(
        "Retrieve an approved answer for a customer FAQ question from the "
        "knowledge base. Returns grounded text with source IDs and provenance. "
        "Abstains safely when no approved source matches."
    ),
    structured_output=True,
)
async def faq_retrieve(query: str) -> dict[str, Any]:
    """Retrieve an approved FAQ answer."""
    answer = knowledge.answer(query)
    return {
        "text": answer.text,
        "status": answer.status.value,
        "reason": answer.reason,
        "source_ids": list(answer.source_ids),
    }


# ---------------------------------------------------------------------------
# Tool: Service catalog
# ---------------------------------------------------------------------------


@server.tool(
    name="service_catalog",
    description=(
        "Look up approved service catalog information (price, duration, "
        "availability status) for a named service. Returns grounded text with "
        "source IDs and provenance."
    ),
    structured_output=True,
)
async def service_catalog(service_id: str) -> dict[str, Any]:
    """Look up service catalog information."""
    answer = knowledge.answer(f"What is the price and duration of {service_id}?")
    return {
        "text": answer.text,
        "status": answer.status.value,
        "reason": answer.reason,
        "source_ids": list(answer.source_ids),
    }


# ---------------------------------------------------------------------------
# Tool: Recorded synthetic availability (read-only)
# ---------------------------------------------------------------------------

availability = AvailabilityService()


@server.tool(
    name="availability_check",
    description=(
        "Check recorded synthetic appointment availability for a service on a "
        "specific date. Read-only: does not book or modify appointments. "
        "Returns recorded slot times or a safe clarification/unsupported "
        "message."
    ),
    structured_output=True,
)
async def availability_check(
    service_id: str, requested_date: str
) -> dict[str, Any]:
    """Check recorded synthetic availability (read-only)."""
    result = availability.lookup(service_id=service_id, requested_date=requested_date)
    return {
        "status": result.status.value,
        "reason": result.reason,
        "service_id": result.service_id,
        "requested_date": str(result.requested_date) if result.requested_date else None,
        "slots": [
            {
                "slot_id": slot.slot_id,
                "service_id": slot.service_id,
                "starts_at": slot.starts_at.isoformat(),
                "ends_at": slot.ends_at.isoformat(),
                "capacity": slot.capacity,
            }
            for slot in result.slots
        ],
        "source_reference": result.source_reference,
    }


# ---------------------------------------------------------------------------
# Tool: Support information (with confirmation safeguards)
# ---------------------------------------------------------------------------


@server.tool(
    name="support_info",
    description=(
        "Retrieve support guidance for the customer. Returns deterministic "
        "unsupported-booking or human-handoff guidance. Does NOT create "
        "tickets without explicit confirmation through the pending-handoff "
        "flow."
    ),
    structured_output=True,
)
async def support_info(intent: str) -> dict[str, Any]:
    """Retrieve support guidance."""
    from backend.intent import Intent

    if intent == Intent.APPOINTMENT_CREATE.value:
        return {
            "intent": Intent.APPOINTMENT_CREATE.value,
            "text": "I can check the recorded slots, but I can't book an appointment in this demo.",
            "outcome": "handoff_unavailable",
            "booking_supported": False,
        }
    if intent == Intent.APPOINTMENT_MODIFY.value:
        return {
            "intent": Intent.APPOINTMENT_MODIFY.value,
            "text": "I can't access or change existing appointments in this demo. No booking was changed.",
            "outcome": "handoff_unavailable",
            "booking_supported": False,
        }
    if intent == Intent.HUMAN_REQUEST.value:
        return {
            "intent": Intent.HUMAN_REQUEST.value,
            "text": "Would you like me to create a queued support ticket for staff to follow up? Please reply yes or no.",
            "outcome": "handoff_unavailable",
            "ticket_creation_requires_confirmation": True,
        }
    return {
        "intent": "unknown",
        "text": "I couldn't safely understand that request. Please rephrase or ask one question at a time.",
        "outcome": "clarification",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run() -> None:
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await server._lowlevel_server.run(
            read_stream, write_stream, server._lowlevel_server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(run())
