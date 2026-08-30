from __future__ import annotations

from typing import Any, Callable

from .warehouse_data import DOCUMENTS, LEDGER_EVENTS, SNAPSHOTS, TICKETS


def get_ticket(ticket_id: str) -> dict[str, Any]:
    """Return the incident record for a ticket ID."""
    ticket = TICKETS.get(ticket_id)
    if ticket is None:
        return {"error": f"No ticket found for {ticket_id}"}
    return ticket


def query_ledger(
    ticket_id: str | None = None, sku: str | None = None, location: str | None = None
) -> list[dict[str, Any]] | dict[str, str]:
    """Return ledger events newest first; ticket results can contain unrelated activity that must be reconciled."""
    if not ticket_id and not sku and not location:
        return {"error": "query_ledger requires ticket_id, sku, or location"}
    result = LEDGER_EVENTS
    if ticket_id:
        result = [event for event in result if event["ticket_id"] == ticket_id]
    elif sku:
        result = [event for event in result if event["sku"] == sku]
    if location:
        result = [event for event in result if event["location"] == location]
    return sorted(result, key=lambda event: event.get("timestamp", ""), reverse=True)


def get_document(document_id: str) -> dict[str, Any]:
    """Return a transfer, sales order, or cycle-count document."""
    document = DOCUMENTS.get(document_id)
    if document is None:
        return {"error": f"No document found for {document_id}"}
    return document


def get_snapshot(sku: str, location: str) -> dict[str, Any]:
    """Return the latest quantities plus older snapshots for the same SKU and location."""
    matches = sorted(
        (
            snapshot
            for snapshot in SNAPSHOTS
            if snapshot["sku"] == sku and snapshot["location"] == location
        ),
        key=lambda snapshot: snapshot.get("captured_at", ""),
        reverse=True,
    )
    if matches:
        return {**matches[0], "history": matches[1:]}
    return {"error": f"No stock snapshot found for {sku} at {location}"}


TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "get_ticket": get_ticket,
    "query_ledger": query_ledger,
    "get_document": get_document,
    "get_snapshot": get_snapshot,
}

TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": "get_ticket", "description": get_ticket.__doc__, "parameters": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]}}},
    {"type": "function", "function": {"name": "query_ledger", "description": query_ledger.__doc__, "parameters": {"type": "object", "properties": {"ticket_id": {"type": "string"}, "sku": {"type": "string"}, "location": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_document", "description": get_document.__doc__, "parameters": {"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]}}},
    {"type": "function", "function": {"name": "get_snapshot", "description": get_snapshot.__doc__, "parameters": {"type": "object", "properties": {"sku": {"type": "string"}, "location": {"type": "string"}}, "required": ["sku", "location"]}}},
]


def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return function(**arguments)
    except TypeError as error:
        return {"error": f"Invalid arguments for {name}: {error}"}
