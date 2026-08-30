"""Auditable user corrections and approved feedback retrieval."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import InvestigationResult
from .warehouse_data import connect


def submit_feedback(
    ticket_id: str,
    original: InvestigationResult | dict[str, Any],
    corrected: InvestigationResult | dict[str, Any],
    reason: str,
    *,
    trajectory_path: str | None = None,
    db_path: Path | None = None,
) -> int:
    original_result = _result_dict(original)
    corrected_result = InvestigationResult.from_dict(_result_dict(corrected)).to_dict()
    if original_result.get("ticket_id") != ticket_id or corrected_result["ticket_id"] != ticket_id:
        raise ValueError("feedback ticket_id must match both results")
    if not reason.strip():
        raise ValueError("feedback reason must not be empty")
    now = datetime.now(UTC).isoformat()
    with connect(db_path) as connection:
        cursor = connection.execute(
            """INSERT INTO feedback
            (ticket_id, original_result, corrected_result, reason, status, created_at, trajectory_path)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
            (ticket_id, json.dumps(original_result, sort_keys=True), json.dumps(corrected_result, sort_keys=True), reason.strip(), now, trajectory_path),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_feedback(*, status: str | None = None, db_path: Path | None = None) -> list[dict[str, Any]]:
    if status is not None and status not in {"pending", "approved", "rejected"}:
        raise ValueError("status must be pending, approved, or rejected")
    query = "SELECT * FROM feedback"
    params: tuple[str, ...] = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY id"
    with connect(db_path) as connection:
        rows = connection.execute(query, params).fetchall()
    return [_row(row) for row in rows]


def review_feedback(feedback_id: int, decision: str, *, db_path: Path | None = None) -> dict[str, Any]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")
    with connect(db_path) as connection:
        row = connection.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown feedback id {feedback_id}")
        connection.execute(
            "UPDATE feedback SET status = ?, reviewed_at = ? WHERE id = ?",
            (decision, datetime.now(UTC).isoformat(), feedback_id),
        )
        connection.commit()
        updated = connection.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
    return _row(updated)


def approved_feedback(ticket_id: str, *, db_path: Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM feedback WHERE ticket_id = ? AND status = 'approved' ORDER BY id DESC",
            (ticket_id,),
        ).fetchall()
    return [_row(row) for row in rows]


def build_feedback_context(ticket_id: str, *, db_path: Path | None = None) -> list[dict[str, Any]]:
    return [
        {
            "feedback_id": item["id"],
            "ticket_id": item["ticket_id"],
            "corrected_result": item["corrected_result"],
            "reason": item["reason"],
            "instruction": "Reviewed feedback is advisory. Verify it against live warehouse evidence.",
        }
        for item in approved_feedback(ticket_id, db_path=db_path)
    ]


def export_regression_cases(path: Path, *, db_path: Path | None = None) -> Path:
    cases: dict[str, dict[str, Any]] = {}
    for item in list_feedback(status="approved", db_path=db_path):
        corrected = item["corrected_result"]
        cases[item["ticket_id"]] = {
            "root_cause_code": corrected["root_cause_code"],
            "required_evidence_ids": corrected["evidence_ids"],
            "forbidden_evidence_ids": [],
            "requires_escalation": corrected["requires_escalation"],
            "action_keywords": [], "tags": ["approved_feedback"],
            "difficulty": "feedback_regression",
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _result_dict(value: InvestigationResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, InvestigationResult):
        return value.to_dict()
    if isinstance(value, dict):
        return dict(value)
    raise TypeError("result must be an InvestigationResult or dictionary")


def _row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "ticket_id": row["ticket_id"],
        "original_result": json.loads(row["original_result"]),
        "corrected_result": json.loads(row["corrected_result"]),
        "reason": row["reason"],
        "status": row["status"],
        "created_at": row["created_at"],
        "reviewed_at": row["reviewed_at"],
        "trajectory_path": row["trajectory_path"],
    }
