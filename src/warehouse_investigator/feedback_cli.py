from __future__ import annotations

import argparse
import json
from pathlib import Path

from .feedback import export_regression_cases, list_feedback, review_feedback, submit_feedback
from .models import InvestigationResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review warehouse investigation feedback.")
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("ticket_id")
    submit.add_argument("--original", type=Path, required=True, help="JSON investigation result")
    submit.add_argument("--corrected", type=Path, required=True, help="JSON corrected result")
    submit.add_argument("--reason", required=True)
    submit.add_argument("--trajectory-path")
    listing = sub.add_parser("list")
    listing.add_argument("--status", choices=("pending", "approved", "rejected"))
    for decision in ("approve", "reject"):
        command = sub.add_parser(decision)
        command.add_argument("feedback_id", type=int)
    export = sub.add_parser("export-regressions")
    export.add_argument("path", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "submit":
        original = json.loads(args.original.read_text(encoding="utf-8"))
        corrected = InvestigationResult.from_dict(json.loads(args.corrected.read_text(encoding="utf-8")))
        feedback_id = submit_feedback(args.ticket_id, original, corrected, args.reason, trajectory_path=args.trajectory_path)
        print(json.dumps({"feedback_id": feedback_id, "status": "pending"}, indent=2))
    elif args.command == "list":
        print(json.dumps(list_feedback(status=args.status), indent=2))
    elif args.command == "export-regressions":
        print(json.dumps({"path": str(export_regression_cases(args.path))}, indent=2))
    else:
        decision = "approved" if args.command == "approve" else "rejected"
        print(json.dumps(review_feedback(args.feedback_id, decision), indent=2))


if __name__ == "__main__":
    main()
