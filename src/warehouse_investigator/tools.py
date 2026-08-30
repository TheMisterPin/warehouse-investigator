from __future__ import annotations

from typing import Any, Callable

from . import warehouse_data
from .index import DEFAULT_SEARCH_LIMIT, RECORD_TYPES, search


def get_ticket(ticket_id: str) -> dict[str, Any]:
    """Return the incident record for a ticket ID."""
    ticket = warehouse_data.get_ticket(ticket_id)
    if ticket is None:
        return {"error": f"No ticket found for {ticket_id}"}
    return ticket


def query_ledger(
    ticket_id: str | None = None, sku: str | None = None, location: str | None = None
) -> list[dict[str, Any]] | dict[str, str]:
    """Return ledger events newest first; ticket results can contain unrelated activity that must be reconciled."""
    if not ticket_id and not sku and not location:
        return {"error": "query_ledger requires ticket_id, sku, or location"}
    return warehouse_data.query_ledger(ticket_id=ticket_id, sku=sku, location=location)


def get_document(document_id: str) -> dict[str, Any]:
    """Return a transfer, sales order, or cycle-count document."""
    document = warehouse_data.get_document(document_id)
    if document is None:
        return {"error": f"No document found for {document_id}"}
    return document


def get_snapshot(sku: str, location: str) -> dict[str, Any]:
    """Return the latest quantities plus older snapshots for the same SKU and location."""
    matches = warehouse_data.query_snapshots(sku, location)
    if matches:
        return {**matches[0], "history": matches[1:]}
    return {"error": f"No stock snapshot found for {sku} at {location}"}


def search_records(
    query: str | None = None, record_type: str | None = None, n: int | None = None
) -> list[dict[str, Any]] | dict[str, str]:
    """Semantically search tickets, ledger events, documents, and snapshots. Optional record_type: ticket, ledger_event, document, snapshot."""
    if not query:
        return {"error": "search_records requires query"}
    if record_type and record_type not in RECORD_TYPES:
        return {"error": f"record_type must be one of {', '.join(RECORD_TYPES)}"}
    limit = DEFAULT_SEARCH_LIMIT if n is None else n
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return {"error": "n must be an integer"}
    try:
        return search(query, record_type=record_type, n=limit)
    except Exception as error:
        return {"error": f"search_records failed: {error}"}


TOOL_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "get_ticket": get_ticket,
    "query_ledger": query_ledger,
    "get_document": get_document,
    "get_snapshot": get_snapshot,
    "search_records": search_records,
}

TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": "get_ticket", "description": get_ticket.__doc__, "parameters": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]}}},
    {"type": "function", "function": {"name": "query_ledger", "description": query_ledger.__doc__, "parameters": {"type": "object", "properties": {"ticket_id": {"type": "string"}, "sku": {"type": "string"}, "location": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_document", "description": get_document.__doc__, "parameters": {"type": "object", "properties": {"document_id": {"type": "string"}}, "required": ["document_id"]}}},
    {"type": "function", "function": {"name": "get_snapshot", "description": get_snapshot.__doc__, "parameters": {"type": "object", "properties": {"sku": {"type": "string"}, "location": {"type": "string"}}, "required": ["sku", "location"]}}},
    {"type": "function", "function": {"name": "search_records", "description": search_records.__doc__, "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "record_type": {"type": "string", "enum": list(RECORD_TYPES)}, "n": {"type": "integer", "minimum": 1, "maximum": 20}}, "required": ["query"]}}},
]


def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return function(**arguments)
    except TypeError as error:
        return {"error": f"Invalid arguments for {name}: {error}"}
