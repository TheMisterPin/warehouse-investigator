from __future__ import annotations

from dataclasses import replace
from typing import Any

from .context import _relevant_ledger_event, _ticket_from_steps
from .models import InvestigationResult

INSUFFICIENT_ACTION = (
    "Escalate to locate the missing document and reconstruct the movement; "
    "do not post a receipt from incomplete records."
)
CONFLICT_ACTION = "Escalate to review why the expected quantity conflicts with the current snapshot."
NO_DISCREPANCY_ACTION = "No action required. Close the ticket and monitor reserved quantity."
PENDING_POST_ACTION = "Post the approved count adjustment."


def finalize_outcome(
    outcome: InvestigationResult, steps: list[dict[str, Any]]
) -> tuple[InvestigationResult, bool, list[str]]:
    flags = evidence_flags_from_steps(steps)
    evidence_ids = _filter_citations(outcome.evidence_ids, steps)
    evidence_ids = _add_partial_remainder_ids(evidence_ids, steps)
    reasons: list[str] = []
    if evidence_ids != list(outcome.evidence_ids):
        reasons.append("citations")
    pinned = False
    root_cause = outcome.root_cause_code
    action = outcome.recommended_action
    confidence = outcome.confidence
    requires_escalation = outcome.requires_escalation

    if "duplicate_event" not in flags:
        if "missing_document" in flags:
            pinned = True
            reasons.append("missing_document")
            root_cause = "INSUFFICIENT_EVIDENCE"
            requires_escalation = True
            confidence = min(confidence, 0.7)
            action = INSUFFICIENT_ACTION
        elif "conflicting_stock" in flags:
            pinned = True
            reasons.append("conflicting_stock")
            root_cause = "INSUFFICIENT_EVIDENCE"
            requires_escalation = True
            confidence = min(confidence, 0.7)
            action = CONFLICT_ACTION
        elif "posted_release" in flags:
            pinned = True
            reasons.append("posted_release")
            root_cause = "NO_DISCREPANCY"
            requires_escalation = False
            confidence = max(confidence, 0.8)
            action = NO_DISCREPANCY_ACTION
        elif "partial_transfer" in flags:
            pinned = True
            reasons.append("partial_transfer")
            root_cause = "PARTIAL_TRANSFER_RECEIPT"
            requires_escalation = False
            confidence = max(confidence, 0.8)
        elif "pending_post" in flags:
            pinned = True
            reasons.append("pending_post")
            root_cause = "COUNT_ADJUSTMENT_NOT_POSTED"
            requires_escalation = False
            confidence = max(confidence, 0.8)
            if "post" not in action.lower() and "adjustment" not in action.lower():
                action = PENDING_POST_ACTION

    finalized = replace(
        outcome,
        root_cause_code=root_cause,
        evidence_ids=evidence_ids,
        recommended_action=action,
        confidence=confidence,
        requires_escalation=requires_escalation,
    )
    return finalized, pinned, reasons


def evidence_flags_from_steps(steps: list[dict[str, Any]]) -> set[str]:
    flags: set[str] = set()
    ticket: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None
    documents: list[dict[str, Any]] = []
    ledger_events: list[dict[str, Any]] = []
    for step in steps:
        if step.get("type") != "tool":
            continue
        name = step.get("name")
        result = step.get("result")
        if name == "get_ticket" and isinstance(result, dict) and "error" not in result:
            ticket = result
        elif name == "get_snapshot" and isinstance(result, dict) and "error" not in result:
            snapshot = result
        elif name == "get_document" and isinstance(result, dict):
            if "error" in result:
                flags.add("missing_document")
            else:
                documents.append(result)
        elif name == "query_ledger" and isinstance(result, list):
            ledger_events.extend(event for event in result if isinstance(event, dict))

    if ticket and len(ticket.get("document_refs", [])) > 1:
        flags.add("multiple_documents")
    if any(document.get("status") == "partially_received" for document in documents):
        flags.add("partial_transfer")
    if any(event.get("state") == "failed" for event in ledger_events) or any(
        document.get("reservation_release_status") == "failed" for document in documents
    ):
        flags.add("failed_workflow")
    if any(event.get("state") == "pending_post" for event in ledger_events):
        flags.add("pending_post")
    if (
        snapshot is not None
        and snapshot.get("reserved_quantity") == 0
        and any(
            event.get("event_type") == "reservation_released" and event.get("state") == "posted"
            for event in ledger_events
        )
    ):
        flags.add("posted_release")
    if any(event.get("retry_of") for event in ledger_events) or _has_duplicate_effect(ledger_events):
        flags.add("duplicate_event")

    completed_transfer_ids = {
        document.get("id")
        for document in documents
        if document.get("type") == "transfer"
        and document.get("status") == "received"
        and ticket
        and document.get("sku") == ticket.get("sku")
        and document.get("destination_location") == ticket.get("location")
    }
    posted_receipt = any(
        event.get("event_type") == "transfer_received"
        and event.get("state") == "posted"
        and event.get("quantity_delta", 0) > 0
        and event.get("document_id") in completed_transfer_ids
        and ticket
        and event.get("sku") == ticket.get("sku")
        and event.get("location") == ticket.get("location")
        for event in ledger_events
    )
    if (
        ticket
        and snapshot
        and completed_transfer_ids
        and posted_receipt
        and ticket.get("expected_quantity") != snapshot.get("physical_quantity")
    ):
        flags.add("conflicting_stock")
    return flags


def _filter_citations(evidence_ids: list[str], steps: list[dict[str, Any]]) -> list[str]:
    allowed = _allowed_citation_ids(steps)
    if not allowed:
        return []
    filtered = [item for item in evidence_ids if item in allowed]
    return filtered


def _allowed_citation_ids(steps: list[dict[str, Any]]) -> set[str]:
    ticket = _ticket_from_steps(steps)
    if ticket is None:
        return set()
    allowed = {ticket["id"], *(ticket.get("document_refs") or [])}
    for step in steps:
        if step.get("type") != "tool":
            continue
        name = step.get("name")
        arguments = step.get("arguments") or {}
        result = step.get("result")
        if name == "get_snapshot" and isinstance(result, dict) and "error" not in result:
            if arguments.get("sku") == ticket.get("sku") and arguments.get("location") == ticket.get("location"):
                if result.get("snapshot_id"):
                    allowed.add(result["snapshot_id"])
        elif name == "query_ledger" and isinstance(result, list):
            for event in result:
                if isinstance(event, dict) and event.get("id") and _relevant_ledger_event(event, ticket):
                    allowed.add(event["id"])
                    if event.get("document_id"):
                        allowed.add(event["document_id"])
        elif name == "get_document" and arguments.get("document_id") in set(ticket.get("document_refs") or []):
            allowed.add(arguments["document_id"])
            if isinstance(result, dict) and result.get("id"):
                allowed.add(result["id"])
    return allowed


def _add_partial_remainder_ids(evidence_ids: list[str], steps: list[dict[str, Any]]) -> list[str]:
    ticket = _ticket_from_steps(steps)
    partial_ids = {
        (step.get("arguments") or {}).get("document_id") or (step.get("result") or {}).get("id")
        for step in steps
        if step.get("type") == "tool"
        and step.get("name") == "get_document"
        and isinstance(step.get("result"), dict)
        and step["result"].get("status") == "partially_received"
    }
    extra: list[str] = []
    for step in steps:
        if step.get("type") != "tool" or step.get("name") != "query_ledger" or not isinstance(step.get("result"), list):
            continue
        for event in step["result"]:
            if not isinstance(event, dict):
                continue
            if (
                event.get("event_type") == "transfer_received"
                and event.get("state") == "pending"
                and event.get("document_id") in partial_ids
                and event.get("id")
                and (ticket is None or _relevant_ledger_event(event, ticket))
            ):
                extra.append(event["id"])
    merged = list(evidence_ids)
    seen = set(evidence_ids)
    for item in extra:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


def _has_duplicate_effect(events: list[dict[str, Any]]) -> bool:
    seen: set[tuple[Any, ...]] = set()
    for event in events:
        if event.get("state") != "posted" or event.get("quantity_delta") in (None, 0):
            continue
        signature = (
            event.get("event_type"),
            event.get("document_id"),
            event.get("location"),
            event.get("quantity_delta"),
        )
        if signature in seen:
            return True
        seen.add(signature)
    return False
