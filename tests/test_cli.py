import json
import sys
from pathlib import Path

from warehouse_investigator.agent import InvestigationRun
from warehouse_investigator.cli import main
from warehouse_investigator.models import InvestigationResult


class FakeInvestigator:
    model = "qwen3:8b"

    def investigate_with_trace(self, ticket_id: str, max_turns: int, trajectory_dir: Path | None) -> InvestigationRun:
        return InvestigationRun(
            model=self.model,
            elapsed_ms=1000,
            tokens={"prompt": 10, "completion": 5, "total": 15},
            outcome=InvestigationResult(
                ticket_id=ticket_id,
                root_cause_code="TRANSFER_NOT_RECEIVED",
                summary="Transfer is in transit.",
                evidence_ids=["TR-100"],
                recommended_action="Complete receiving at SEA-01.",
                confidence=0.95,
                requires_escalation=False,
            ),
            steps=[],
            trajectory_path=None,
        )


def test_cli_prints_investigating_status_to_stderr(monkeypatch, capsys) -> None:
    monkeypatch.setattr("warehouse_investigator.cli.create_investigator", lambda **_kwargs: FakeInvestigator())
    monkeypatch.setattr(sys, "argv", ["investigate", "INC-001", "--no-log"])

    main()

    captured = capsys.readouterr()
    assert "Investigating INC-001" in captured.err
    assert "Incident INC-001" in captured.out


def test_cli_keeps_json_stdout_parseable(monkeypatch, capsys) -> None:
    monkeypatch.setattr("warehouse_investigator.cli.create_investigator", lambda **_kwargs: FakeInvestigator())
    monkeypatch.setattr(sys, "argv", ["investigate", "INC-001", "--format", "json", "--no-log"])

    main()

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["outcome"]["ticket_id"] == "INC-001"
    assert "Investigating INC-001" in captured.err
