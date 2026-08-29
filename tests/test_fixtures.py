from warehouse_investigator.models import ROOT_CAUSE_CODES
from warehouse_investigator.evaluation_data import EVALUATION_CASES
from warehouse_investigator.warehouse_data import DOCUMENTS, LEDGER_EVENTS, SNAPSHOTS, TICKETS


def test_expanded_fixture_set_is_complete() -> None:
    expected_ids = [f"INC-{number:03d}" for number in range(1, 13)]
    assert list(TICKETS) == expected_ids
    assert list(EVALUATION_CASES) == expected_ids


def test_operational_data_is_separated_and_contains_noise() -> None:
    incident_events = [event for event in LEDGER_EVENTS if event["ticket_id"] == "INC-001"]

    assert len(incident_events) > len(EVALUATION_CASES["INC-001"]["required_evidence_ids"])
    assert any(event["sku"] != TICKETS["INC-001"]["sku"] for event in incident_events)
    assert all("root_cause_code" not in ticket for ticket in TICKETS.values())
    assert len(SNAPSHOTS) > len(TICKETS)
    assert DOCUMENTS


def test_case_expectations_use_supported_codes_and_safety_fields() -> None:
    for expected in EVALUATION_CASES.values():
        assert expected["root_cause_code"] in ROOT_CAUSE_CODES
        assert "forbidden_evidence_ids" in expected
        assert "forbidden_action_keywords" in expected
        assert 0 <= expected["confidence"]["min"] <= expected["confidence"]["max"] <= 1
        assert expected["tags"]
        assert expected["difficulty"] in {"easy", "medium", "hard"}
