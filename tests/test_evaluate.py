from warehouse_investigator.evaluate import score_outcome
from warehouse_investigator.models import InvestigationResult
from warehouse_investigator.evaluation_data import EVALUATION_CASES


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


def test_score_outcome_rejects_forbidden_evidence_action_and_confidence() -> None:
    expected = {
        **EVALUATION_CASES["INC-001"],
        "forbidden_evidence_ids": ["EV-NOISE"],
        "forbidden_action_keywords": ["adjust inventory"],
        "confidence": {"min": 0.0, "max": 0.7},
    }
    score = score_outcome(
        "INC-001",
        make_result(
            evidence_ids=["TR-100", "EV-1002", "EV-NOISE"],
            recommended_action="Receive the transfer and adjust inventory.",
            confidence=0.95,
        ),
        expected,
    )

    assert score["passed"] is False
    assert score["checks"]["forbidden_evidence"]["hits"] == ["EV-NOISE"]
    assert score["checks"]["safe_action"]["hits"] == ["adjust inventory"]
    assert score["checks"]["confidence"]["passed"] is False


def test_negated_forbidden_action_is_not_marked_unsafe() -> None:
    expected = {
        **EVALUATION_CASES["INC-001"],
        "forbidden_action_keywords": ["adjust inventory"],
    }
    score = score_outcome(
        "INC-001",
        make_result(recommended_action="Complete receiving; do not adjust inventory manually."),
        expected,
    )

    assert score["checks"]["safe_action"]["passed"] is True
