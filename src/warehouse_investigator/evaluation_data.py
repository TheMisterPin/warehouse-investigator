"""Load evaluator-only ground truth that is never exposed through warehouse tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


GROUND_TRUTH_PATH = Path(__file__).parent / "data" / "evaluation" / "ground_truth.json"


def load_evaluation_cases(path: Path = GROUND_TRUTH_PATH) -> dict[str, dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not value:
        raise ValueError(f"Evaluation dataset {path} must contain a non-empty JSON object")
    for ticket_id, expected in value.items():
        if not ticket_id.startswith("INC-") or not isinstance(expected, dict):
            raise ValueError(f"Invalid evaluation case {ticket_id!r} in {path}")
        for required in ("root_cause_code", "required_evidence_ids", "forbidden_evidence_ids"):
            if required not in expected:
                raise ValueError(f"Evaluation case {ticket_id} is missing {required}")
    return value


EVALUATION_CASES = load_evaluation_cases()
GROUND_TRUTH = {ticket_id: expected["root_cause_code"] for ticket_id, expected in EVALUATION_CASES.items()}

