from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, TextIO

from .agent import Investigator
from .factory import create_investigator
from .models import InvestigationResult
from .routing import RoutedInvestigator
from .evaluation_data import EVALUATION_CASES


def score_outcome(ticket_id: str, result: InvestigationResult, expected: dict[str, Any]) -> dict[str, Any]:
    evidence_ids = set(result.evidence_ids)
    required_evidence = set(expected.get("required_evidence_ids", []))
    forbidden_evidence = set(expected.get("forbidden_evidence_ids", []))
    forbidden_evidence_hits = sorted(forbidden_evidence & evidence_ids)
    action = result.recommended_action.lower()
    action_keywords = expected.get("action_keywords", [])
    unsafe_action_hits = _unsafe_action_hits(action, expected.get("forbidden_action_keywords", []))
    confidence = expected.get("confidence", {"min": 0.0, "max": 1.0})
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
        "forbidden_evidence": {
            "passed": not forbidden_evidence_hits,
            "forbidden": sorted(forbidden_evidence),
            "actual": result.evidence_ids,
            "hits": forbidden_evidence_hits,
        },
        "recommended_action": {
            "passed": len(result.recommended_action.strip()) >= 10
            and (not action_keywords or any(keyword in action for keyword in action_keywords)),
            "expected_any_keyword": action_keywords,
            "actual": result.recommended_action,
        },
        "safe_action": {
            "passed": not unsafe_action_hits,
            "forbidden_keywords": expected.get("forbidden_action_keywords", []),
            "hits": unsafe_action_hits,
            "actual": result.recommended_action,
        },
        "confidence": {
            "passed": confidence["min"] <= result.confidence <= confidence["max"],
            "expected": confidence,
            "actual": result.confidence,
        },
        "escalation": {
            "passed": result.requires_escalation == expected["requires_escalation"],
            "expected": expected["requires_escalation"],
            "actual": result.requires_escalation,
        },
    }
    return {"passed": all(check["passed"] for check in checks.values()), "checks": checks}


def run_evaluation(
    investigator: Investigator | RoutedInvestigator,
    runs_per_case: int,
    max_turns: int,
    trajectory_dir: Path,
    case_ids: list[str] | None = None,
    workers: int = 2,
    progress_interval_seconds: float = 1,
) -> dict[str, Any]:
    if runs_per_case < 1:
        raise ValueError("runs_per_case must be at least 1")
    if workers < 1:
        raise ValueError("workers must be at least 1")
    started_at = datetime.now(UTC)
    started_perf = perf_counter()
    selected_cases = EVALUATION_CASES
    if case_ids:
        unknown = sorted(set(case_ids) - set(EVALUATION_CASES))
        if unknown:
            raise ValueError(f"Unknown case IDs: {', '.join(unknown)}")
        selected_cases = {ticket_id: EVALUATION_CASES[ticket_id] for ticket_id in dict.fromkeys(case_ids)}

    jobs = [
        (ticket_id, expected, repetition)
        for ticket_id, expected in selected_cases.items()
        for repetition in range(1, runs_per_case + 1)
    ]
    results: list[dict[str, Any] | None] = [None] * len(jobs)
    labels = [_job_label(ticket_id, repetition, runs_per_case) for ticket_id, _, repetition in jobs]
    board = EvaluationBoard(labels, interval_seconds=progress_interval_seconds)

    def run_job(index: int, ticket_id: str, expected: dict[str, Any], repetition: int) -> tuple[int, dict[str, Any]]:
        label = labels[index]
        board.mark_working(label)
        try:
            run = investigator.investigate_with_trace(ticket_id, max_turns, trajectory_dir)
            score = score_outcome(ticket_id, run.outcome, expected)
            record = {
                "ticket_id": ticket_id,
                "repetition": repetition,
                "tags": expected.get("tags", []),
                "difficulty": expected.get("difficulty", "unclassified"),
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
                "tags": expected.get("tags", []),
                "difficulty": expected.get("difficulty", "unclassified"),
                "passed": False,
                "checks": {},
                "model": investigator.model,
                "elapsed_ms": None,
                "tokens": {"prompt": 0, "completion": 0, "total": 0},
                "outcome": None,
                "step_count": 0,
                "trajectory_path": None,
                "error": str(error),
            }
        board.mark_finished(label, record)
        return index, record

    board.start()
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(run_job, index, ticket_id, expected, repetition)
                for index, (ticket_id, expected, repetition) in enumerate(jobs)
            ]
            for future in as_completed(futures):
                index, record = future.result()
                results[index] = record
    finally:
        board.close()

    return _build_report(
        investigator.model,
        runs_per_case,
        max_turns,
        started_at,
        started_perf,
        [record for record in results if record is not None],
        selected_cases,
        workers,
    )


def compare_reports(current: dict[str, Any], previous: dict[str, Any], previous_path: Path) -> dict[str, Any]:
    current_cases = current["summary"]["cases"]
    previous_cases = previous.get("summary", {}).get("cases", {})
    common = sorted(set(current_cases) & set(previous_cases))
    previous_summary = previous.get("summary", {})
    current_summary = current["summary"]
    previous_config = previous.get("configuration") or {}
    current_config = current.get("configuration") or {}
    return {
        "previous_report": str(previous_path),
        "previous_model": previous.get("model"),
        "previous_workers": previous_config.get("workers"),
        "current_workers": current_config.get("workers"),
        "previous_pass_rate": previous_summary.get("pass_rate"),
        "current_pass_rate": current_summary["pass_rate"],
        "pass_rate_delta": _optional_delta(current_summary["pass_rate"], previous_summary.get("pass_rate")),
        "previous_wall_clock_seconds": previous_summary.get("wall_clock_seconds"),
        "current_wall_clock_seconds": current_summary.get("wall_clock_seconds"),
        "wall_clock_delta": _optional_delta(
            current_summary.get("wall_clock_seconds"), previous_summary.get("wall_clock_seconds")
        ),
        "previous_mean_run_seconds": previous_summary.get("mean_run_seconds"),
        "current_mean_run_seconds": current_summary.get("mean_run_seconds"),
        "mean_run_delta": _optional_delta(
            current_summary.get("mean_run_seconds"), previous_summary.get("mean_run_seconds")
        ),
        "common_cases": {
            ticket_id: {
                "previous_pass_rate": previous_cases[ticket_id]["pass_rate"],
                "current_pass_rate": current_cases[ticket_id]["pass_rate"],
                "delta": round(current_cases[ticket_id]["pass_rate"] - previous_cases[ticket_id]["pass_rate"], 4),
            }
            for ticket_id in common
        },
        "new_cases": sorted(set(current_cases) - set(previous_cases)),
        "removed_cases": sorted(set(previous_cases) - set(current_cases)),
    }


def save_report(report: dict[str, Any], report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    model_name = re.sub(r"[^A-Za-z0-9._-]+", "-", report["model"])
    path = report_dir / f"evaluation_{model_name}_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_report(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or "summary" not in value:
        raise ValueError(f"Comparison report {path} has no summary")
    return value


def _build_report(
    model: str,
    runs_per_case: int,
    max_turns: int,
    started_at: datetime,
    started_perf: float,
    results: list[dict[str, Any]],
    selected_cases: dict[str, dict[str, Any]],
    workers: int = 2,
) -> dict[str, Any]:
    completed = [record for record in results if record["elapsed_ms"] is not None]
    passed = sum(record["passed"] for record in results)
    total_tokens = sum(record["tokens"]["total"] for record in results)
    case_summaries = {
        ticket_id: _summarize_records([record for record in results if record["ticket_id"] == ticket_id])
        for ticket_id in selected_cases
    }
    difficulties = sorted({record["difficulty"] for record in results})
    tags = sorted({tag for record in results for tag in record["tags"]})
    return {
        "created_at": started_at.isoformat(),
        "model": model,
        "configuration": {
            "runs_per_case": runs_per_case,
            "max_turns": max_turns,
            "workers": workers,
            "case_count": len(selected_cases),
            "case_ids": list(selected_cases),
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
            "difficulties": {
                difficulty: _summarize_records([record for record in results if record["difficulty"] == difficulty])
                for difficulty in difficulties
            },
            "tags": {
                tag: _summarize_records([record for record in results if tag in record["tags"]])
                for tag in tags
            },
        },
        "results": results,
    }


def _summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(record["passed"] for record in records)
    return {
        "passed_runs": passed,
        "total_runs": len(records),
        "pass_rate": round(passed / len(records), 4),
    }


def _unsafe_action_hits(action: str, forbidden_keywords: list[str]) -> list[str]:
    hits = []
    for keyword in forbidden_keywords:
        if keyword not in action:
            continue
        negated = any(f"{prefix} {keyword}" in action for prefix in ("do not", "don't", "avoid"))
        if not negated:
            hits.append(keyword)
    return hits


def _optional_delta(current: Any, previous: Any) -> float | None:
    if not isinstance(current, (int, float)) or not isinstance(previous, (int, float)):
        return None
    return round(current - previous, 4)


def _format_comparison(comparison: dict[str, Any]) -> str:
    workers = f"{comparison.get('current_workers')} vs {comparison.get('previous_workers')} workers"
    wall = comparison.get("wall_clock_delta")
    mean_run = comparison.get("mean_run_delta")
    pass_delta = comparison.get("pass_rate_delta")
    if not all(isinstance(value, (int, float)) for value in (wall, mean_run, pass_delta)):
        return f"Compared with {comparison.get('previous_report')}."
    return (
        f"Compared with {comparison.get('previous_report')}: {workers}; "
        f"wall {wall:+.1f}s; mean case {mean_run:+.1f}s; pass rate {pass_delta:+.1%}."
    )


def _failed_check_names(checks: dict[str, Any]) -> str:
    failed = [name for name, check in checks.items() if not check["passed"]]
    return f"failed checks: {', '.join(failed)}" if failed else ""


def _job_label(ticket_id: str, repetition: int, runs_per_case: int) -> str:
    if runs_per_case == 1:
        return ticket_id
    return f"{ticket_id} run {repetition}/{runs_per_case}"


@dataclass
class ProgressRow:
    label: str
    status: str
    started_at: float | None = None
    elapsed_s: float | None = None
    tokens: int | None = None
    outcome: str = ""


_COLOR = {"pass": "\x1b[32m", "fail": "\x1b[31m"}
_RESET = "\x1b[0m"


def format_progress_row(row: ProgressRow, now: float, color: bool = False) -> str:
    if row.status == "working" and row.started_at is not None:
        elapsed = f"{now - row.started_at:.1f}s"
    elif row.elapsed_s is not None:
        elapsed = f"{row.elapsed_s:.1f}s"
    else:
        elapsed = "—"
    tokens = "—" if row.tokens is None else str(row.tokens)
    line = f"{row.label:<16} {row.status:<8} {elapsed:>7} {tokens:>8} tokens  {row.outcome}".rstrip()
    if color and row.status in _COLOR:
        return f"{_COLOR[row.status]}{line}{_RESET}"
    return line


class EvaluationBoard:
    def __init__(
        self,
        labels: list[str],
        stream: TextIO | None = None,
        live: bool | None = None,
        interval_seconds: float = 1,
    ) -> None:
        self.order = labels
        self.rows = {label: ProgressRow(label, "queued") for label in labels}
        self.stream = stream or sys.stdout
        self.live = self.stream.isatty() if live is None else live
        self.interval_seconds = interval_seconds
        self.drawn = False
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._ticker: threading.Thread | None = None

    def start(self) -> None:
        self.render()
        if self.live and self.interval_seconds > 0:
            self._ticker = threading.Thread(target=self._tick, name="evaluation-board", daemon=True)
            self._ticker.start()

    def mark_working(self, label: str) -> None:
        with self.lock:
            row = self.rows[label]
            row.status = "working"
            row.started_at = perf_counter()
        self.render()

    def mark_finished(self, label: str, record: dict[str, Any]) -> None:
        elapsed_ms = record.get("elapsed_ms")
        with self.lock:
            row = self.rows[label]
            row.status = "pass" if record.get("passed") else "fail"
            row.elapsed_s = None if elapsed_ms is None else elapsed_ms / 1000
            row.tokens = (record.get("tokens") or {}).get("total")
            row.outcome = (record.get("outcome") or {}).get("root_cause_code") or record.get("error") or ""
        self.render()

    def close(self) -> None:
        self._stop.set()
        if self._ticker is not None:
            self._ticker.join(timeout=0.2)
        self.render()
        if self.live and self.drawn:
            self.stream.write("\x1b[?25h")
            self.stream.flush()

    def render(self) -> None:
        if not self.live:
            return
        now = perf_counter()
        with self.lock:
            lines = [format_progress_row(self.rows[label], now, color=True) for label in self.order]
        if self.drawn:
            self.stream.write(f"\x1b[{len(lines)}A")
        else:
            self.stream.write("\x1b[?25l")
        for line in lines:
            self.stream.write(f"\x1b[2K{line}\n")
        self.stream.flush()
        self.drawn = True

    def _tick(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.render()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the warehouse-investigator challenge evaluation.")
    parser.add_argument("--model", default="auto", help="Use auto routing (default) or one fixed Ollama model")
    parser.add_argument("--primary-model", help="Primary fast tier (default: qwen3:8b)")
    parser.add_argument("--deep-model", help="Deep-review tier (default: qwen3.5:27b)")
    parser.add_argument("--host", help="Ollama host")
    parser.add_argument("--runs", type=int, default=1, help="Repetitions per case (default: 1)")
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--workers", type=int, default=2, help="Concurrent ticket investigations (default: 2)")
    parser.add_argument("--trajectory-dir", type=Path, default=Path("trajectories/evaluation"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    parser.add_argument("--compare-to", type=Path, help="Previous JSON report to compare against")
    parser.add_argument("--case", dest="case_ids", action="append", help="Run only this case ID; may be repeated")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    investigator = create_investigator(
        model=args.model,
        host=args.host,
        primary_model=args.primary_model,
        deep_model=args.deep_model,
    )
    try:
        report = run_evaluation(
            investigator, args.runs, args.max_turns, args.trajectory_dir, args.case_ids, args.workers
        )
        if args.compare_to:
            report["comparison"] = compare_reports(report, load_report(args.compare_to), args.compare_to)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"Evaluation failed: {error}") from error
    report_path = save_report(report, args.report_dir)
    summary = report["summary"]
    print(
        f"\nEvaluation: {summary['passed_runs']}/{summary['total_runs']} runs passed "
        f"({summary['pass_rate']:.0%}); {summary['total_tokens']} tokens; "
        f"{summary['wall_clock_seconds']}s wall clock."
    )
    comparison = report.get("comparison")
    if comparison:
        print(_format_comparison(comparison))
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
