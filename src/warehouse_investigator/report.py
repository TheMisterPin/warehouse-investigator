from __future__ import annotations

from typing import Any


def format_result_text(run: dict[str, Any]) -> str:
    """Render a single investigation run as an incident note a person could act on directly."""
    outcome = run["outcome"]
    lines = [
        f"Incident {outcome['ticket_id']} — {outcome['root_cause_code']}",
        f"Confidence: {outcome['confidence']:.0%}   Escalation required: {'yes' if outcome['requires_escalation'] else 'no'}",
        "",
        "Summary:",
        f"  {outcome['summary']}",
        "",
        "Evidence:",
    ]
    if outcome["evidence_ids"]:
        lines.extend(f"  - {evidence_id}" for evidence_id in outcome["evidence_ids"])
    else:
        lines.append("  (none cited)")
    lines.extend(
        [
            "",
            "Recommended action:",
            f"  {outcome['recommended_action']}",
            "",
            "-" * 44,
            f"Model: {run['model']}   Time: {run['time']['elapsed_seconds']}s   Tokens: {run['tokens']['total']}",
        ]
    )
    if run.get("trajectory_path"):
        lines.append(f"Trajectory: {run['trajectory_path']}")
    return "\n".join(lines)


def format_batch_text(entries: list[dict[str, Any]]) -> str:
    """Render a queue of investigations as a summary table, one row per ticket."""
    columns = (("TICKET", 10), ("ROOT CAUSE", 26), ("CONF", 5), ("ESCALATE", 8), ("TIME", 8))
    header = " ".join(f"{name:<{width}}" for name, width in columns[:-1]) + f" {columns[-1][0]:>{columns[-1][1]}}"
    lines = [header, "-" * len(header)]
    for entry in entries:
        ticket_id = entry["ticket_id"]
        if entry.get("error"):
            lines.append(f"{ticket_id:<10} FAILED: {entry['error']}")
            continue
        outcome = entry["run"]["outcome"]
        confidence = f"{outcome['confidence']:.0%}"
        escalate = "yes" if outcome["requires_escalation"] else "no"
        time_s = f"{entry['run']['time']['elapsed_seconds']}s"
        lines.append(
            f"{ticket_id:<10} {outcome['root_cause_code']:<26} {confidence:>5} {escalate:>8} {time_s:>8}"
        )
    return "\n".join(lines)
