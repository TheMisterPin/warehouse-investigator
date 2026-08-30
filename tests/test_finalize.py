from warehouse_investigator.finalize import finalize_outcome
from warehouse_investigator.models import InvestigationResult
from warehouse_investigator.tools import execute_tool


def make_outcome(**overrides) -> InvestigationResult:
    values = {
        "ticket_id": "INC-001",
        "root_cause_code": "TRANSFER_NOT_RECEIVED",
        "summary": "Fixture diagnosis.",
        "evidence_ids": ["TR-100", "EV-1002"],
        "recommended_action": "Complete receiving.",
        "confidence": 0.95,
        "requires_escalation": False,
    }
    values.update(overrides)
    return InvestigationResult(**values)


def tool_steps(ticket_id: str) -> list[dict]:
    ticket = execute_tool("get_ticket", {"ticket_id": ticket_id})
    ledger = execute_tool("query_ledger", {"ticket_id": ticket_id})
    snapshot = execute_tool("get_snapshot", {"sku": ticket["sku"], "location": ticket["location"]})
    steps = [
        {"type": "tool", "name": "get_ticket", "arguments": {"ticket_id": ticket_id}, "result": ticket},
        {"type": "tool", "name": "query_ledger", "arguments": {"ticket_id": ticket_id}, "result": ledger},
        {
            "type": "tool",
            "name": "get_snapshot",
            "arguments": {"sku": ticket["sku"], "location": ticket["location"]},
            "result": snapshot,
        },
    ]
    for document_id in ticket.get("document_refs") or []:
        steps.append(
            {
                "type": "tool",
                "name": "get_document",
                "arguments": {"document_id": document_id},
                "result": execute_tool("get_document", {"document_id": document_id}),
            }
        )
    return steps


def test_drops_historical_ids_outside_the_investigation_window() -> None:
    outcome, pinned, reasons = finalize_outcome(
        make_outcome(
            ticket_id="INC-003",
            root_cause_code="PENDING_CYCLE_COUNT",
            evidence_ids=["EV-3001", "EV-H003A", "EV-H003B", "CC-300"],
            recommended_action="Approve the cycle count.",
        ),
        tool_steps("INC-003"),
    )

    assert outcome.evidence_ids == ["EV-3001", "CC-300"]
    assert "EV-H003A" not in outcome.evidence_ids
    assert pinned is False
    assert "citations" in reasons


def test_missing_document_pins_insufficient_evidence() -> None:
    outcome, pinned, reasons = finalize_outcome(
        make_outcome(
            ticket_id="INC-006",
            root_cause_code="TRANSFER_NOT_RECEIVED",
            evidence_ids=["EV-6001", "EV-6002"],
            recommended_action="Post the pending transfer receipt.",
            confidence=0.85,
        ),
        tool_steps("INC-006"),
    )

    assert pinned is True
    assert "missing_document" in reasons
    assert outcome.root_cause_code == "INSUFFICIENT_EVIDENCE"
    assert outcome.requires_escalation is True
    assert outcome.confidence <= 0.7
    assert {"EV-6001", "EV-6002"}.issubset(set(outcome.evidence_ids))
    assert "locate" in outcome.recommended_action.lower()


def test_conflicting_stock_pins_insufficient_evidence() -> None:
    outcome, pinned, reasons = finalize_outcome(
        make_outcome(
            ticket_id="INC-012",
            root_cause_code="NO_DISCREPANCY",
            evidence_ids=["EV-12001", "EV-12002", "TR-203", "SNAP-012-LATEST"],
            recommended_action="Close the ticket as resolved.",
            confidence=0.95,
            requires_escalation=False,
        ),
        tool_steps("INC-012"),
    )

    assert pinned is True
    assert "conflicting_stock" in reasons
    assert outcome.root_cause_code == "INSUFFICIENT_EVIDENCE"
    assert outcome.requires_escalation is True
    assert outcome.confidence <= 0.7


def test_duplicate_event_is_not_overridden_to_insufficient() -> None:
    outcome, pinned, _reasons = finalize_outcome(
        make_outcome(
            ticket_id="INC-005",
            root_cause_code="DUPLICATE_LEDGER_EVENT",
            evidence_ids=["EV-5002", "EV-5003", "TR-201"],
            recommended_action="Reverse the duplicate receipt.",
            requires_escalation=True,
        ),
        tool_steps("INC-005"),
    )

    assert pinned is False
    assert outcome.root_cause_code == "DUPLICATE_LEDGER_EVENT"


def test_posted_release_pins_no_discrepancy() -> None:
    outcome, pinned, reasons = finalize_outcome(
        make_outcome(
            ticket_id="INC-007",
            root_cause_code="STALE_RESERVATION",
            evidence_ids=["EV-7001", "EV-7002", "EV-7003", "SO-901"],
            recommended_action="Release the stale reservation.",
        ),
        tool_steps("INC-007"),
    )

    assert pinned is True
    assert "posted_release" in reasons
    assert outcome.root_cause_code == "NO_DISCREPANCY"
    assert outcome.requires_escalation is False
    assert outcome.confidence >= 0.8
    assert "release the reservation" not in outcome.recommended_action.lower()
    assert "EV-7003" in outcome.evidence_ids


def test_partial_transfer_pins_cause_and_adds_pending_receipt() -> None:
    outcome, pinned, reasons = finalize_outcome(
        make_outcome(
            ticket_id="INC-004",
            root_cause_code="TRANSFER_NOT_RECEIVED",
            evidence_ids=["TR-200", "EV-4001", "EV-4002"],
            recommended_action="Complete receiving for the remaining units.",
        ),
        tool_steps("INC-004"),
    )

    assert pinned is True
    assert "partial_transfer" in reasons
    assert outcome.root_cause_code == "PARTIAL_TRANSFER_RECEIPT"
    assert "EV-4003" in outcome.evidence_ids
    assert "TR-200" in outcome.evidence_ids
    assert "EV-4002" in outcome.evidence_ids


def test_pending_post_pins_count_adjustment_not_posted() -> None:
    outcome, pinned, reasons = finalize_outcome(
        make_outcome(
            ticket_id="INC-010",
            root_cause_code="PENDING_CYCLE_COUNT",
            evidence_ids=["CC-302", "EV-10001", "EV-10002"],
            recommended_action="Approve the count.",
        ),
        tool_steps("INC-010"),
    )

    assert pinned is True
    assert "pending_post" in reasons
    assert outcome.root_cause_code == "COUNT_ADJUSTMENT_NOT_POSTED"
    assert outcome.requires_escalation is False
    assert "post" in outcome.recommended_action.lower()
