from warehouse_investigator.tools import execute_tool


def test_incident_one_fixture_has_transfer_evidence() -> None:
    ticket = execute_tool("get_ticket", {"ticket_id": "INC-001"})
    document = execute_tool("get_document", {"document_id": ticket["document_refs"][0]})
    ledger = execute_tool("query_ledger", {"ticket_id": "INC-001"})

    assert document["status"] == "in_transit"
    assert any(event["event_type"] == "transfer_shipped" for event in ledger)
    assert any(event["sku"] != ticket["sku"] for event in ledger)


def test_snapshot_returns_latest_record_with_history() -> None:
    snapshot = execute_tool("get_snapshot", {"sku": "SKU-RED-CHAIR", "location": "SEA-01"})

    assert snapshot["captured_at"] == "2026-08-27T14:55:00Z"
    assert snapshot["history"]
    assert all(item["captured_at"] < snapshot["captured_at"] for item in snapshot["history"])
