from warehouse_investigator.report import format_batch_text, format_result_text


def make_run_dict(ticket_id: str = "INC-001", confidence: float = 0.95, escalation: bool = False) -> dict:
    return {
        "model": "qwen3:8b",
        "time": {"elapsed_ms": 7973, "elapsed_seconds": 7.973},
        "tokens": {"prompt": 100, "completion": 20, "total": 120},
        "outcome": {
            "ticket_id": ticket_id,
            "root_cause_code": "TRANSFER_NOT_RECEIVED",
            "summary": "Transfer is in transit; destination receipt not posted.",
            "evidence_ids": ["TR-100", "EV-1002"],
            "recommended_action": "Complete receiving at SEA-01.",
            "confidence": confidence,
            "requires_escalation": escalation,
        },
        "steps": [],
        "trajectory_path": "trajectories/INC-001_20260828T220304Z.json",
    }


def test_format_result_text_reads_like_an_incident_note() -> None:
    text = format_result_text(make_run_dict())

    assert "Incident INC-001 — TRANSFER_NOT_RECEIVED" in text
    assert "Confidence: 95%" in text
    assert "Escalation required: no" in text
    assert "- TR-100" in text
    assert "- EV-1002" in text
    assert "Complete receiving at SEA-01." in text
    assert "Model: qwen3:8b" in text
    assert "Trajectory: trajectories/INC-001_20260828T220304Z.json" in text
    assert '"ticket_id"' not in text
    assert "elapsed_ms" not in text


def test_format_result_text_handles_no_cited_evidence() -> None:
    run = make_run_dict()
    run["outcome"]["evidence_ids"] = []

    text = format_result_text(run)

    assert "(none cited)" in text


def test_format_batch_text_lists_one_row_per_ticket() -> None:
    entries = [
        {"ticket_id": "INC-001", "run": make_run_dict("INC-001"), "error": None},
        {"ticket_id": "INC-999", "run": None, "error": "No ticket found for 'INC-999'. Check the ticket ID and try again."},
    ]

    text = format_batch_text(entries)
    lines = text.splitlines()

    assert lines[0].startswith("TICKET")
    assert any(line.startswith("INC-001") and "TRANSFER_NOT_RECEIVED" in line for line in lines)
    assert any(line.startswith("INC-999") and "FAILED" in line for line in lines)
