import json

from warehouse_investigator.feedback import (
    approved_feedback,
    build_feedback_context,
    export_regression_cases,
    list_feedback,
    review_feedback,
    submit_feedback,
)
from warehouse_investigator.models import InvestigationResult


def _result(code: str = "NO_DISCREPANCY") -> InvestigationResult:
    return InvestigationResult("INC-001", code, "summary", ["TR-100"], "No action required.", 0.8, False)


def test_feedback_requires_approval_and_is_retrievable(tmp_path):
    db = tmp_path / "warehouse.db"
    feedback_id = submit_feedback("INC-001", _result(), _result("TRANSFER_NOT_RECEIVED"), "The receipt is missing", db_path=db)
    assert list_feedback(db_path=db)[0]["status"] == "pending"
    assert build_feedback_context("INC-001", db_path=db) == []
    reviewed = review_feedback(feedback_id, "approved", db_path=db)
    assert reviewed["status"] == "approved"
    context = build_feedback_context("INC-001", db_path=db)
    assert context[0]["corrected_result"]["root_cause_code"] == "TRANSFER_NOT_RECEIVED"
    assert len(approved_feedback("INC-001", db_path=db)) == 1
    output = export_regression_cases(tmp_path / "regressions.json", db_path=db)
    assert json.loads(output.read_text())["INC-001"]["root_cause_code"] == "TRANSFER_NOT_RECEIVED"


def test_feedback_persists_json_results(tmp_path):
    db = tmp_path / "warehouse.db"
    submit_feedback("INC-001", _result(), _result(), "verified", db_path=db)
    record = list_feedback(db_path=db)[0]
    assert json.loads(json.dumps(record["original_result"]))["ticket_id"] == "INC-001"
