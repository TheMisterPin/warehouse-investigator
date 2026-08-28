from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from .agent import Investigator
from .models import InvestigationResult
from .ollama import OllamaClient
from .sample_data import EVALUATION_CASES


def score_outcome(ticket_id: str, result: InvestigationResult, expected: dict[str, Any]) -> dict[str, Any]:
    evidence_ids = set(result.evidence_ids)
    required_evidence = set(expected["required_evidence_ids"])
    action = result.recommended_action.lower()
    checks = {
        "ticket_id": {
            "passed": result.ticket_id == ticket_id,
            "expected": ticket_id,
            "actual": result.ticket_id,
        },
        "root_cause": {
            "passed": result.root_cause_code == expected["root_cause_code"],
            "expected": expected["root_cause_code"],
            "actual": result.root_cause_code,
        },
        "required_evidence": {
            "passed": required_evidence.issubset(evidence_ids),
            "required": sorted(required_evidence),
            "actual": result.evidence_ids,
            "missing": sorted(required_evidence - evidence_ids),
        },
        "recommended_action": {
            "passed": len(result.recommended_action.strip()) >= 10
            and any(keyword in action for keyword in expected["action_keywords"]),
            "expected_any_keyword": expected["action_keywords"],
            "actual": result.recommended_action,
        },
        "escalation": {
            "passed": result.requires_escalation == expected["requires_escalation"],
            "expected": expected["requires_escalation"],
            "actual": result.requires_escalation,
        },
    }
    return {"passed": all(check["passed"] for check in checks.values()), "checks": checks}


def run_evaluation(
    investigator: Investigator,
    runs_per_case: int,
    max_turns: int,
    trajectory_dir: Path,
) -> dict[str, Any]:
    if runs_per_case < 1:
        raise ValueError("runs_per_case must be at least 1")
    started_at = datetime.now(UTC)
    started_perf = perf_counter()
    results: list[dict[str, Any]] = []

    for ticket_id, expected in EVALUATION_CASES.items():
        for repetition in range(1, runs_per_case + 1):
            try:
                run = investigator.investigate_with_trace(ticket_id, max_turns, trajectory_dir)
                score = score_outcome(ticket_id, run.outcome, expected)
                record = {
                    "ticket_id": ticket_id,
                    "repetition": repetition,
                    "passed": score["passed"],
                    "checks": score["checks"],
                    "model": run.model,
                    "elapsed_ms": run.elapsed_ms,
                    "tokens": run.tokens,
                    "outcome": run.outcome.to_dict(),
                    "step_count": len(run.steps),
                    "trajectory_path": run.trajectory_path,
                    "error": None,
                }
            except Exception as error:
                record = {
                    "ticket_id": ticket_id,
                    "repetition": repetition,
                    "passed": False,
                    "checks": {},
                    "model": investigator.client.model,
                    "elapsed_ms": None,
                    "tokens": {"prompt": 0, "completion": 0, "total": 0},
                    "outcome": None,
                    "step_count": 0,
                    "trajectory_path": None,
                    "error": str(error),
                }
            results.append(record)
            status = "PASS" if record["passed"] else "FAIL"
            detail = record["error"] or _failed_check_names(record["checks"]) or "all checks"
            print(f"{status} {ticket_id} run {repetition}/{runs_per_case}: {detail}", flush=True)

    completed = [record for record in results if record["elapsed_ms"] is not None]
    passed = sum(record["passed"] for record in results)
    total_tokens = sum(record["tokens"]["total"] for record in results)
    case_summaries = {}
    for ticket_id in EVALUATION_CASES:
        case_records = [record for record in results if record["ticket_id"] == ticket_id]
        case_summaries[ticket_id] = {
            "passed_runs": sum(record["passed"] for record in case_records),
            "total_runs": len(case_records),
            "pass_rate": round(sum(record["passed"] for record in case_records) / len(case_records), 4),
        }

    return {
        "created_at": started_at.isoformat(),
        "model": investigator.client.model,
        "configuration": {
            "runs_per_case": runs_per_case,
            "max_turns": max_turns,
            "case_count": len(EVALUATION_CASES),
        },
        "summary": {
            "passed_runs": passed,
            "total_runs": len(results),
            "pass_rate": round(passed / len(results), 4),
            "wall_clock_seconds": round(perf_counter() - started_perf, 3),
            "mean_run_seconds": round(mean(record["elapsed_ms"] for record in completed) / 1000, 3) if completed else None,
            "prompt_tokens": sum(record["tokens"]["prompt"] for record in results),
            "completion_tokens": sum(record["tokens"]["completion"] for record in results),
            "total_tokens": total_tokens,
            "mean_tokens_per_run": round(total_tokens / len(results), 1),
            "cases": case_summaries,
        },
        "results": results,
    }


def save_report(report: dict[str, Any], report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    model_name = re.sub(r"[^A-Za-z0-9._-]+", "-", report["model"])
    path = report_dir / f"baseline_{model_name}_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _failed_check_names(checks: dict[str, Any]) -> str:
    failed = [name for name, check in checks.items() if not check["passed"]]
    return f"failed checks: {', '.join(failed)}" if failed else ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the repeatable warehouse-investigator baseline evaluation.")
    parser.add_argument("--model", help="Ollama model name")
    parser.add_argument("--runs", type=int, default=3, help="Repetitions per case (default: 3)")
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--trajectory-dir", type=Path, default=Path("trajectories/evaluation"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    investigator = Investigator(OllamaClient(model=args.model))
    try:
        report = run_evaluation(investigator, args.runs, args.max_turns, args.trajectory_dir)
    except ValueError as error:
        raise SystemExit(f"Evaluation failed: {error}") from error
    report_path = save_report(report, args.report_dir)
    summary = report["summary"]
    print(
        f"\nBaseline: {summary['passed_runs']}/{summary['total_runs']} runs passed "
        f"({summary['pass_rate']:.0%}); {summary['total_tokens']} tokens; "
        f"{summary['wall_clock_seconds']}s wall clock."
    )
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
