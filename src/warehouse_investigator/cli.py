from __future__ import annotations

import argparse
import json
from pathlib import Path

from .factory import create_investigator
from .ollama import OllamaError
from .report import format_batch_text, format_result_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Investigate one or more warehouse incidents with local Ollama.")
    parser.add_argument("ticket_ids", nargs="+", metavar="ticket_id", help="One or more incident IDs, such as INC-001")
    parser.add_argument("--model", default="auto", help="Use auto routing (default) or one fixed Ollama model")
    parser.add_argument("--primary-model", help="Primary fast tier (default: qwen3:8b)")
    parser.add_argument("--deep-model", help="Deep-review tier (default: qwen3.5:27b)")
    parser.add_argument("--host", help="Ollama host; defaults to OLLAMA_HOST or http://localhost:11434")
    parser.add_argument("--max-turns", type=int, default=12, help="Maximum model/tool turns")
    parser.add_argument("--trajectory-dir", type=Path, default=Path("trajectories"), help="Directory for run logs")
    parser.add_argument("--no-log", action="store_true", help="Do not write a trajectory log")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    investigator = create_investigator(
        model=args.model,
        host=args.host,
        primary_model=args.primary_model,
        deep_model=args.deep_model,
    )

    results: list[dict] = []
    for ticket_id in args.ticket_ids:
        try:
            run = investigator.investigate_with_trace(
                ticket_id,
                max_turns=args.max_turns,
                trajectory_dir=None if args.no_log else args.trajectory_dir,
            )
            results.append({"ticket_id": ticket_id, "run": run.to_dict(), "error": None})
        except (OllamaError, RuntimeError, ValueError) as error:
            results.append({"ticket_id": ticket_id, "run": None, "error": str(error)})

    single = len(results) == 1
    failures = [entry for entry in results if entry["error"] is not None]

    if single and failures:
        raise SystemExit(f"Investigation failed: {failures[0]['error']}")

    if args.format == "json":
        payload = results[0]["run"] if single else {"results": results}
        print(json.dumps(payload, indent=2))
    elif single:
        print(format_result_text(results[0]["run"]))
    else:
        print(format_batch_text(results))

    if failures and len(failures) == len(results):
        raise SystemExit(1)
