from __future__ import annotations

import argparse
from pathlib import Path

from .agent import Investigator
from .ollama import OllamaClient
from .sample_data import GROUND_TRUTH


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixed warehouse-investigator evaluation cases.")
    parser.add_argument("--model", help="Ollama model name")
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--trajectory-dir", type=Path, default=Path("trajectories/evaluation"))
    args = parser.parse_args()
    investigator = Investigator(OllamaClient(model=args.model))
    correct = 0
    for ticket_id, expected in GROUND_TRUTH.items():
        result = investigator.investigate(ticket_id, args.max_turns, args.trajectory_dir)
        passed = result.root_cause_code == expected
        correct += passed
        mark = "PASS" if passed else "FAIL"
        print(f"{mark} {ticket_id}: expected={expected} actual={result.root_cause_code}")
    print(f"\nScore: {correct}/{len(GROUND_TRUTH)}")
