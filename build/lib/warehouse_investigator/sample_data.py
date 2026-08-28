"""Load deterministic warehouse cases from individual JSON fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CASE_DIR = Path(__file__).parent / "data" / "cases"


def load_cases(case_dir: Path = CASE_DIR) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for path in sorted(case_dir.glob("INC-*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        ticket_id = case.get("ticket", {}).get("id")
        if not ticket_id:
            raise ValueError(f"Case fixture {path} has no ticket.id")
        if ticket_id != path.stem:
            raise ValueError(f"Case fixture {path} contains ticket {ticket_id}")
        if ticket_id in cases:
            raise ValueError(f"Duplicate case fixture for {ticket_id}")
        for required in ("ledger_events", "documents", "snapshots", "expected"):
            if required not in case:
                raise ValueError(f"Case fixture {path} is missing {required}")
        cases[ticket_id] = case
    if not cases:
        raise ValueError(f"No case fixtures found in {case_dir}")
    return cases


CASES = load_cases()
TICKETS = {ticket_id: case["ticket"] for ticket_id, case in CASES.items()}
LEDGER_EVENTS = [event for case in CASES.values() for event in case["ledger_events"]]
DOCUMENTS = {document["id"]: document for case in CASES.values() for document in case["documents"]}
SNAPSHOTS = [snapshot for case in CASES.values() for snapshot in case["snapshots"]]
EVALUATION_CASES = {ticket_id: case["expected"] for ticket_id, case in CASES.items()}
GROUND_TRUTH = {ticket_id: expected["root_cause_code"] for ticket_id, expected in EVALUATION_CASES.items()}
