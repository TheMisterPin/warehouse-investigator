import json

from warehouse_investigator.context import (
    build_model_messages,
    compact_tool_result,
    new_evidence,
    record_evidence,
    select_review_evidence,
)
from warehouse_investigator.tools import execute_tool, get_snapshot


def test_snapshot_omits_history_when_quantities_match_latest() -> None:
    snapshot = get_snapshot("SKU-RED-CHAIR", "SEA-01")
    compacted = compact_tool_result("get_snapshot", snapshot)

    assert compacted["snapshot_id"] == "SNAP-001-LATEST"
    assert "history" not in compacted


def test_snapshot_keeps_history_rows_with_different_quantities() -> None:
    snapshot = {
        "sku": "SKU-RED-CHAIR",
        "location": "SEA-01",
        "physical_quantity": 94,
        "reserved_quantity": 0,
        "available_quantity": 94,
        "captured_at": "2026-08-27T14:55:00Z",
        "snapshot_id": "SNAP-001-LATEST",
        "history": [
            {
                "sku": "SKU-RED-CHAIR",
                "location": "SEA-01",
                "physical_quantity": 90,
                "reserved_quantity": 0,
                "available_quantity": 90,
                "captured_at": "2026-08-20T15:00:00Z",
                "snapshot_id": "SNAP-001-HISTORICAL",
            }
        ],
    }

    compacted = compact_tool_result("get_snapshot", snapshot)

    assert compacted["history"][0]["snapshot_id"] == "SNAP-001-HISTORICAL"


def test_unfiltered_ledger_query_returns_error() -> None:
    result = execute_tool("query_ledger", {})

    assert result == {"error": "query_ledger requires ticket_id, sku, or location"}


def test_model_messages_use_one_evidence_bundle_and_gate_status() -> None:
    evidence = new_evidence()
    ticket = execute_tool("get_ticket", {"ticket_id": "INC-001"})
    ledger = execute_tool("query_ledger", {"ticket_id": "INC-001"})
    record_evidence(evidence, "get_ticket", {"ticket_id": "INC-001"}, ticket, "INC-001")
    record_evidence(evidence, "query_ledger", {"ticket_id": "INC-001"}, ledger, "INC-001")

    messages = build_model_messages("INC-001", "Investigate carefully.", evidence)
    bundle = json.loads(messages[-1]["content"])

    assert messages[0] == {"role": "system", "content": "Investigate carefully."}
    assert messages[1]["content"] == "Investigate warehouse incident INC-001."
    assert len(messages) == 3
    assert bundle["ticket_id"] == "INC-001"
    assert bundle["retrieved"]["ticket"]["id"] == "INC-001"
    assert any(event["id"] == "EV-X001" for event in bundle["retrieved"]["ledger"])
    assert bundle["evidence_gate"]["complete"] is False
    assert "get_snapshot(ticket.sku, ticket.location)" in bundle["evidence_gate"]["missing"]
    assert "search_records" not in " ".join(bundle["evidence_gate"]["missing"])
    assert bundle["retrieved"]["search"] == []
    assert "Evidence gate is incomplete" not in json.dumps(messages)


def test_review_filter_keeps_ticket_relevant_records_only() -> None:
    ticket = execute_tool("get_ticket", {"ticket_id": "INC-001"})
    ledger = execute_tool("query_ledger", {"ticket_id": "INC-001"})
    snapshot = execute_tool("get_snapshot", {"sku": "SKU-RED-CHAIR", "location": "SEA-01"})
    steps = [
        {"type": "tool", "name": "get_ticket", "arguments": {"ticket_id": "INC-001"}, "result": ticket},
        {"type": "tool", "name": "query_ledger", "arguments": {"ticket_id": "INC-001"}, "result": ledger},
        {"type": "tool", "name": "get_snapshot", "arguments": {"sku": "SKU-RED-CHAIR", "location": "SEA-01"}, "result": snapshot},
        {"type": "tool", "name": "get_document", "arguments": {"document_id": "TR-100"}, "result": {"id": "TR-100", "status": "in_transit"}},
        {"type": "tool", "name": "get_document", "arguments": {"document_id": "TR-X001"}, "result": {"id": "TR-X001", "sku": "SKU-NOISE-001"}},
        {"type": "tool", "name": "get_document", "arguments": {"document_id": "TR-MISSING"}, "result": {"error": "No document found for TR-MISSING"}},
    ]

    filtered = select_review_evidence(steps)
    ledger_ids = [event["id"] for item in filtered if item["tool"] == "query_ledger" for event in item["result"]]
    document_ids = [item["arguments"]["document_id"] for item in filtered if item["tool"] == "get_document"]
    snapshot_item = next(item for item in filtered if item["tool"] == "get_snapshot")

    assert "EV-1001" in ledger_ids
    assert "EV-1002" in ledger_ids
    assert "EV-X001" not in ledger_ids
    assert "EV-H001A" not in ledger_ids
    assert document_ids == ["TR-100"]
    assert "history" not in snapshot_item["result"]


def test_review_filter_keeps_missing_ticket_document_errors() -> None:
    ticket = {
        "id": "INC-006",
        "sku": "SKU-YELLOW-BENCH",
        "location": "SEA-01",
        "document_refs": ["TR-MISSING"],
        "investigation_window_start": "2026-08-26T19:00:00Z",
        "reported_at": "2026-08-27T19:00:00Z",
    }
    steps = [
        {"type": "tool", "name": "get_ticket", "arguments": {"ticket_id": "INC-006"}, "result": ticket},
        {
            "type": "tool",
            "name": "get_document",
            "arguments": {"document_id": "TR-MISSING"},
            "result": {"error": "No document found for TR-MISSING"},
        },
    ]

    filtered = select_review_evidence(steps)

    assert filtered[-1]["result"] == {"error": "No document found for TR-MISSING"}


def test_search_results_are_included_in_the_evidence_bundle() -> None:
    evidence = new_evidence()
    ticket = execute_tool("get_ticket", {"ticket_id": "INC-001"})
    hits = execute_tool("search_records", {"query": "TR-100", "record_type": "document", "n": 3})
    record_evidence(evidence, "get_ticket", {"ticket_id": "INC-001"}, ticket, "INC-001")
    record_evidence(evidence, "search_records", {"query": "TR-100", "record_type": "document", "n": 3}, hits, "INC-001")

    bundle = json.loads(build_model_messages("INC-001", "Investigate carefully.", evidence)[-1]["content"])

    assert bundle["retrieved"]["search"]
    assert bundle["retrieved"]["search"][0]["query"] == "TR-100"
    assert any(hit["record"]["id"] == "TR-100" for hit in bundle["retrieved"]["search"][0]["results"])
    assert "search_records" not in " ".join(bundle["evidence_gate"]["missing"])
