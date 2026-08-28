from warehouse_investigator.evaluate import score_outcome
from warehouse_investigator.models import InvestigationResult
from warehouse_investigator.sample_data import EVALUATION_CASES


def make_result(**overrides) -> InvestigationResult:
    values = {
        "ticket_id": "INC-001",
        "root_cause_code": "TRANSFER_NOT_RECEIVED",
        "summary": "The destination receipt is pending.",
        "evidence_ids": ["TR-100", "EV-1002"],
        "recommended_action": "Complete receiving for the transfer.",
        "confidence": 0.95,
        "requires_escalation": False,
    }
    values.update(overrides)
    return InvestigationResult(**values)


def test_score_outcome_passes_complete_diagnosis() -> None:
    score = score_outcome("INC-001", make_result(), EVALUATION_CASES["INC-001"])

    assert score["passed"] is True
    assert all(check["passed"] for check in score["checks"].values())


def test_score_outcome_rejects_missing_evidence() -> None:
    score = score_outcome(
        "INC-001",
        make_result(evidence_ids=["TR-100"]),
        EVALUATION_CASES["INC-001"],
    )

    assert score["passed"] is False
    assert score["checks"]["required_evidence"]["missing"] == ["EV-1002"]
