from warehouse_investigator.models import ROOT_CAUSE_CODES
from warehouse_investigator.evaluation_data import EVALUATION_CASES
from warehouse_investigator.warehouse_data import list_documents, list_ledger_events, list_snapshots, list_tickets


def test_expanded_fixture_set_is_complete() -> None:
    expected_ids = [f"INC-{number:03d}" for number in range(1, 13)]
    assert list(list_tickets()) == expected_ids
    assert list(EVALUATION_CASES) == expected_ids


def test_operational_data_is_separated_and_contains_noise() -> None:
    tickets = list_tickets()
    incident_events = [event for event in list_ledger_events() if event["ticket_id"] == "INC-001"]

    assert len(incident_events) > len(EVALUATION_CASES["INC-001"]["required_evidence_ids"])
    assert any(event["sku"] != tickets["INC-001"]["sku"] for event in incident_events)
    assert all("root_cause_code" not in ticket for ticket in tickets.values())
    assert len(list_snapshots()) > len(tickets)
    assert list_documents()


def test_case_expectations_use_supported_codes_and_safety_fields() -> None:
    for expected in EVALUATION_CASES.values():
        assert expected["root_cause_code"] in ROOT_CAUSE_CODES
        assert "forbidden_evidence_ids" in expected
        assert "forbidden_action_keywords" in expected
        assert 0 <= expected["confidence"]["min"] <= expected["confidence"]["max"] <= 1
        assert expected["tags"]
        assert expected["difficulty"] in {"easy", "medium", "hard"}
