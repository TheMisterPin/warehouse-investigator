from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent import Investigator
from .ollama import OllamaClient, OllamaError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Investigate a warehouse incident with local Ollama.")
    parser.add_argument("ticket_id", help="Incident ID, such as INC-001")
    parser.add_argument("--model", help="Ollama model name; defaults to OLLAMA_MODEL or qwen3-coder:30b")
    parser.add_argument("--host", help="Ollama host; defaults to OLLAMA_HOST or http://localhost:11434")
    parser.add_argument("--max-turns", type=int, default=12, help="Maximum model/tool turns")
    parser.add_argument("--trajectory-dir", type=Path, default=Path("trajectories"), help="Directory for run logs")
    parser.add_argument("--no-log", action="store_true", help="Do not write a trajectory log")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = OllamaClient(model=args.model, host=args.host)
    investigator = Investigator(client)
    try:
        run = investigator.investigate_with_trace(
            args.ticket_id,
            max_turns=args.max_turns,
            trajectory_dir=None if args.no_log else args.trajectory_dir,
        )
    except (OllamaError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Investigation failed: {error}") from error
    print(json.dumps(run.to_dict(), indent=2))
