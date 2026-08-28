from warehouse_investigator.models import ROOT_CAUSE_CODES
from warehouse_investigator.sample_data import CASES, EVALUATION_CASES


def test_expanded_fixture_set_is_complete() -> None:
    assert list(CASES) == [f"INC-{number:03d}" for number in range(1, 13)]


def test_case_expectations_use_supported_codes_and_safety_fields() -> None:
    for expected in EVALUATION_CASES.values():
        assert expected["root_cause_code"] in ROOT_CAUSE_CODES
        assert "forbidden_evidence_ids" in expected
        assert "forbidden_action_keywords" in expected
        assert 0 <= expected["confidence"]["min"] <= expected["confidence"]["max"] <= 1
        assert expected["tags"]
        assert expected["difficulty"] in {"easy", "medium", "hard"}
