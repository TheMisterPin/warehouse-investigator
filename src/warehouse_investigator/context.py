from __future__ import annotations

import json
from typing import Any


QUANTITY_FIELDS = ("physical_quantity", "reserved_quantity", "available_quantity")
ALREADY_FETCHED = {"status": "already_fetched"}


def new_evidence() -> dict[str, Any]:
    return {
        "ticket": None,
        "ledger": False,
        "ledger_result": None,
        "snapshot": False,
        "snapshot_result": None,
        "documents": {},
        "document_attempts": set(),
        "seen_calls": set(),
        "searches": [],
    }


def tool_call_key(name: str, arguments: dict[str, Any]) -> tuple[Any, ...]:
    return (name, json.dumps(arguments, sort_keys=True, separators=(",", ":")))


def already_fetched(evidence: dict[str, Any], name: str, arguments: dict[str, Any]) -> bool:
    return tool_call_key(name, arguments) in evidence["seen_calls"]


def compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def compact_tool_result(name: str, result: Any) -> Any:
    if name == "get_snapshot" and isinstance(result, dict):
        return _compact_snapshot(result)
    return result


def record_evidence(
    evidence: dict[str, Any], name: str, arguments: dict[str, Any], result: Any, ticket_id: str
) -> None:
    evidence["seen_calls"].add(tool_call_key(name, arguments))
    if not isinstance(result, dict) and name not in {"query_ledger", "search_records"}:
        return
    if name == "get_ticket" and isinstance(result, dict) and result.get("id") == ticket_id:
        evidence["ticket"] = result
    elif name == "query_ledger" and arguments.get("ticket_id") == ticket_id:
        evidence["ledger"] = True
        evidence["ledger_result"] = result if isinstance(result, list) else None
    elif name == "get_snapshot" and evidence["ticket"] and (
        arguments.get("sku") == evidence["ticket"].get("sku")
        and arguments.get("location") == evidence["ticket"].get("location")
    ):
        evidence["snapshot"] = True
        evidence["snapshot_result"] = result if isinstance(result, dict) else None
    elif name == "get_document" and arguments.get("document_id"):
        document_id = arguments["document_id"]
        evidence["document_attempts"].add(document_id)
        evidence["documents"][document_id] = result
    elif name == "search_records":
        evidence["searches"].append(
            {
                "query": arguments.get("query"),
                "record_type": arguments.get("record_type"),
                "n": arguments.get("n"),
                "results": result if isinstance(result, list) else [],
            }
        )


def missing_evidence(evidence: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    ticket = evidence["ticket"]
    if ticket is None:
        return ["get_ticket(ticket_id)"]
    if not evidence["ledger"]:
        missing.append("query_ledger(ticket_id)")
    if not evidence["snapshot"]:
        missing.append("get_snapshot(ticket.sku, ticket.location)")
    for document_id in ticket.get("document_refs", []):
        if document_id not in evidence["document_attempts"]:
            missing.append(f"get_document({document_id})")
    return missing


def evidence_gate_complete(evidence: dict[str, Any]) -> bool:
    return evidence["ticket"] is not None and not missing_evidence(evidence)


def build_model_messages(
    ticket_id: str,
    instructions: str,
    evidence: dict[str, Any],
    feedback: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": f"Investigate warehouse incident {ticket_id}."},
    ]
    if not evidence["seen_calls"] and evidence["ticket"] is None:
        return messages
    missing = missing_evidence(evidence)
    bundle = {
        "ticket_id": ticket_id,
        "reviewed_feedback": feedback or [],
        "retrieved": {
            "ticket": compact_tool_result("get_ticket", evidence["ticket"]) if evidence["ticket"] else None,
            "ledger": compact_tool_result("query_ledger", evidence["ledger_result"])
            if evidence["ledger_result"] is not None
            else None,
            "snapshot": compact_tool_result("get_snapshot", evidence["snapshot_result"])
            if evidence["snapshot_result"] is not None
            else None,
            "documents": {
                document_id: compact_tool_result("get_document", result)
                for document_id, result in evidence["documents"].items()
            },
            "search": evidence.get("searches") or [],
        },
        "evidence_gate": {
            "complete": not missing,
            "missing": missing,
        },
    }
    messages.append({"role": "user", "content": compact_json(bundle)})
    return messages


def select_review_evidence(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ticket = _ticket_from_steps(steps)
    selected: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for step in steps:
        if step.get("type") != "tool":
            continue
        name = step.get("name")
        arguments = step.get("arguments") or {}
        result = step.get("result")
        key = tool_call_key(str(name), arguments if isinstance(arguments, dict) else {})
        if key in seen:
            continue
        filtered = _filter_review_result(str(name), arguments, result, ticket)
        if filtered is None:
            continue
        seen.add(key)
        selected.append({"tool": name, "arguments": arguments, "result": filtered})
    return selected


def _compact_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    if "error" in result or "history" not in result:
        return result
    latest = {field: result.get(field) for field in QUANTITY_FIELDS}
    history = [
        item
        for item in result.get("history") or []
        if isinstance(item, dict) and any(item.get(field) != latest[field] for field in QUANTITY_FIELDS)
    ]
    compacted = {key: value for key, value in result.items() if key != "history"}
    if history:
        compacted["history"] = history
    return compacted


def _ticket_from_steps(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    for step in steps:
        if step.get("type") == "tool" and step.get("name") == "get_ticket":
            result = step.get("result")
            if isinstance(result, dict) and "error" not in result:
                return result
    return None


def _filter_review_result(name: str, arguments: dict[str, Any], result: Any, ticket: dict[str, Any] | None) -> Any:
    if ticket is None:
        return compact_tool_result(name, result)
    document_refs = set(ticket.get("document_refs") or [])
    if name == "get_ticket":
        return compact_tool_result(name, result)
    if name == "get_document":
        document_id = arguments.get("document_id")
        if document_id in document_refs:
            return compact_tool_result(name, result)
        return None
    if name == "get_snapshot":
        if arguments.get("sku") == ticket.get("sku") and arguments.get("location") == ticket.get("location"):
            return compact_tool_result(name, result)
        return None
    if name == "query_ledger" and isinstance(result, list):
        events = [event for event in result if isinstance(event, dict) and _relevant_ledger_event(event, ticket)]
        return events
    if name == "search_records" and isinstance(result, list):
        return [hit for hit in result if isinstance(hit, dict) and _relevant_search_hit(hit, ticket)]
    return None


def _relevant_search_hit(hit: dict[str, Any], ticket: dict[str, Any]) -> bool:
    record = hit.get("record") if isinstance(hit.get("record"), dict) else {}
    if record.get("id") == ticket.get("id"):
        return True
    if record.get("id") in set(ticket.get("document_refs") or []):
        return True
    sku_match = record.get("sku") == ticket.get("sku")
    location = record.get("location") or record.get("destination_location")
    if sku_match and (not location or location == ticket.get("location")):
        return True
    return False


def _relevant_ledger_event(event: dict[str, Any], ticket: dict[str, Any]) -> bool:
    if event.get("sku") != ticket.get("sku"):
        return False
    if event.get("document_id") in set(ticket.get("document_refs") or []):
        return True
    window_start = ticket.get("investigation_window_start") or ticket.get("reported_at")
    timestamp = event.get("timestamp")
    return bool(window_start and timestamp and timestamp >= window_start)
