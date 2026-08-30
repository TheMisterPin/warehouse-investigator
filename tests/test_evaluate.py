import threading
import time
from pathlib import Path

from warehouse_investigator.agent import InvestigationRun
from warehouse_investigator.evaluate import (
    ProgressRow,
    format_progress_row,
    run_evaluation,
    score_outcome,
)
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


class ConcurrentInvestigator:
    model = "stub-model"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def investigate_with_trace(self, ticket_id: str, max_turns: int, trajectory_dir: Path) -> InvestigationRun:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.2)
        with self._lock:
            self.active -= 1
        outcome = InvestigationResult(
            ticket_id=ticket_id,
            root_cause_code="INSUFFICIENT_EVIDENCE",
            summary="Concurrent fixture result.",
            evidence_ids=[],
            recommended_action="Review the ticket.",
            confidence=0.5,
            requires_escalation=True,
        )
        return InvestigationRun(
            model=self.model,
            elapsed_ms=200,
            tokens={"prompt": 1, "completion": 1, "total": 2},
            outcome=outcome,
            steps=[],
            trajectory_path=None,
        )


def test_evaluation_runs_four_tickets_concurrently(tmp_path: Path) -> None:
    investigator = ConcurrentInvestigator()

    report = run_evaluation(
        investigator,
        runs_per_case=1,
        max_turns=12,
        trajectory_dir=tmp_path,
        case_ids=["INC-001", "INC-002", "INC-003", "INC-004"],
        workers=4,
    )

    assert investigator.max_active == 4
    assert report["configuration"]["workers"] == 4
    assert [record["ticket_id"] for record in report["results"]] == ["INC-001", "INC-002", "INC-003", "INC-004"]


def test_progress_row_shows_ticket_status_time_and_tokens() -> None:
    queued = format_progress_row(ProgressRow("INC-001", "queued"), now=0)
    working = format_progress_row(ProgressRow("INC-002", "working", started_at=10.0), now=22.3)
    passed = format_progress_row(
        ProgressRow(
            "INC-003",
            "pass",
            elapsed_s=8.2,
            tokens=4210,
            outcome="PENDING_CYCLE_COUNT",
        ),
        now=0,
    )

    assert queued.startswith("INC-001")
    assert "queued" in queued
    assert "—" in queued
    assert "working" in working
    assert "12.3s" in working
    assert "4210" in passed
    assert "PENDING_CYCLE_COUNT" in passed


def test_finished_progress_rows_use_green_and_red() -> None:
    passed = format_progress_row(
        ProgressRow("INC-001", "pass", elapsed_s=18.2, tokens=8559, outcome="TRANSFER_NOT_RECEIVED"),
        now=0,
        color=True,
    )
    failed = format_progress_row(
        ProgressRow("INC-006", "fail", elapsed_s=45.1, tokens=8900, outcome="INSUFFICIENT_EVIDENCE"),
        now=0,
        color=True,
    )

    assert passed.startswith("\x1b[32m")
    assert "8559" in passed
    assert failed.startswith("\x1b[31m")
    assert "INSUFFICIENT_EVIDENCE" in failed
