from warehouse_investigator.tools import execute_tool


def test_incident_one_fixture_has_transfer_evidence() -> None:
    ticket = execute_tool("get_ticket", {"ticket_id": "INC-001"})
    document = execute_tool("get_document", {"document_id": ticket["document_refs"][0]})
    ledger = execute_tool("query_ledger", {"ticket_id": "INC-001"})

    assert document["status"] == "in_transit"
    assert any(event["event_type"] == "transfer_shipped" for event in ledger)
