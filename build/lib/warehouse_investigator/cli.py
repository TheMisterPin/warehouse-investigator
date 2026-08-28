from __future__ import annotations

import argparse
import json
from pathlib import Path

from .factory import create_investigator
from .ollama import OllamaError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Investigate a warehouse incident with local Ollama.")
    parser.add_argument("ticket_id", help="Incident ID, such as INC-001")
    parser.add_argument("--model", default="auto", help="Use auto routing (default) or one fixed Ollama model")
    parser.add_argument("--routing-profile", choices=("fast", "economy"), default="fast")
    parser.add_argument("--small-model", help="Low-memory tier (default: qwen3:4b)")
    parser.add_argument("--primary-model", help="Primary fast tier (default: qwen3:8b)")
    parser.add_argument("--deep-model", help="Deep-review tier (default: qwen3.5:27b)")
    parser.add_argument("--host", help="Ollama host; defaults to OLLAMA_HOST or http://localhost:11434")
    parser.add_argument("--max-turns", type=int, default=12, help="Maximum model/tool turns")
    parser.add_argument("--trajectory-dir", type=Path, default=Path("trajectories"), help="Directory for run logs")
    parser.add_argument("--no-log", action="store_true", help="Do not write a trajectory log")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    investigator = create_investigator(
        model=args.model,
        host=args.host,
        fast_model=args.small_model,
        balanced_model=args.primary_model,
        deep_model=args.deep_model,
        routing_profile=args.routing_profile,
    )
    try:
        run = investigator.investigate_with_trace(
            args.ticket_id,
            max_turns=args.max_turns,
            trajectory_dir=None if args.no_log else args.trajectory_dir,
        )
    except (OllamaError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Investigation failed: {error}") from error
    print(json.dumps(run.to_dict(), indent=2))
