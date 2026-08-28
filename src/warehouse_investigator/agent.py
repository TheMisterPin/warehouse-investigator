from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import InvestigationResult, RESULT_SCHEMA
from .ollama import OllamaClient
from .tools import TOOL_DEFINITIONS, execute_tool
from .trajectory import TrajectoryLogger


@dataclass(frozen=True)
class InvestigationRun:
    """A completed investigation plus the telemetry needed to audit it."""

    model: str
    elapsed_ms: int
    tokens: dict[str, int]
    outcome: InvestigationResult
    steps: list[dict[str, Any]]
    trajectory_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "time": {
                "elapsed_ms": self.elapsed_ms,
                "elapsed_seconds": round(self.elapsed_ms / 1000, 3),
            },
            "tokens": self.tokens,
            "outcome": self.outcome.to_dict(),
            "steps": self.steps,
            "trajectory_path": self.trajectory_path,
        }


class Investigator:
    def __init__(self, client: OllamaClient, instructions_path: Path | None = None) -> None:
        self.client = client
        self.instructions_path = instructions_path or Path(__file__).parents[2] / "instructions" / "investigator.md"

    def investigate(self, ticket_id: str, max_turns: int = 12, trajectory_dir: Path | None = Path("trajectories")) -> InvestigationResult:
        return self.investigate_with_trace(ticket_id, max_turns, trajectory_dir).outcome

    def investigate_with_trace(
        self, ticket_id: str, max_turns: int = 12, trajectory_dir: Path | None = Path("trajectories")
    ) -> InvestigationRun:
        instructions = self.instructions_path.read_text(encoding="utf-8")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": f"Investigate warehouse incident {ticket_id}."},
        ]
        logger = TrajectoryLogger(ticket_id, trajectory_dir)
        logger.add("run_started", model=self.client.model, max_turns=max_turns)
        tokens = {"prompt": 0, "completion": 0, "total": 0}
        steps: list[dict[str, Any]] = []
        evidence: dict[str, Any] = {"ticket": None, "ledger": False, "snapshot": False, "documents": set()}
        try:
            for turn in range(1, max_turns + 1):
                response_format = RESULT_SCHEMA if _evidence_gate_complete(evidence) else None
                response = self.client.chat(messages, TOOL_DEFINITIONS, response_format)
                message = response.get("message", {})
                prompt_tokens = _as_token_count(response.get("prompt_eval_count"))
                completion_tokens = _as_token_count(response.get("eval_count"))
                tokens["prompt"] += prompt_tokens
                tokens["completion"] += completion_tokens
                tokens["total"] += prompt_tokens + completion_tokens
                logger.add(
                    "model_response",
                    turn=turn,
                    message=message,
                    done_reason=response.get("done_reason"),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
                messages.append(message)
                tool_calls = message.get("tool_calls") or []
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "type": "model",
                        "turn": turn,
                        "elapsed_ms": logger.elapsed_ms,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "content": message.get("content", ""),
                        "tool_calls": [call.get("function", {}) for call in tool_calls],
                    }
                )
                if tool_calls:
                    for call in tool_calls:
                        function = call.get("function", {})
                        name = function.get("name", "")
                        arguments = function.get("arguments", {})
                        if isinstance(arguments, str):
                            arguments = json.loads(arguments)
                        result = execute_tool(name, arguments)
                        _record_evidence(evidence, name, arguments, result, ticket_id)
                        logger.add("tool_call", turn=turn, name=name, arguments=arguments, result=result)
                        steps.append(
                            {
                                "step": len(steps) + 1,
                                "type": "tool",
                                "turn": turn,
                                "elapsed_ms": logger.elapsed_ms,
                                "name": name,
                                "arguments": arguments,
                                "result": result,
                            }
                        )
                        messages.append({"role": "tool", "content": json.dumps(result), "tool_name": name})
                    continue
                if not _evidence_gate_complete(evidence):
                    missing = _missing_evidence(evidence)
                    logger.add("evidence_gate_retry", turn=turn, missing=missing)
                    steps.append(
                        {
                            "step": len(steps) + 1,
                            "type": "system",
                            "turn": turn,
                            "elapsed_ms": logger.elapsed_ms,
                            "message": f"Evidence gate incomplete; continue with tools: {', '.join(missing)}",
                        }
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Evidence gate is incomplete. Call the remaining tools before diagnosing: {', '.join(missing)}.",
                        }
                    )
                    continue
                result = InvestigationResult.from_dict(_parse_json_content(message.get("content", "")))
                if result.ticket_id != ticket_id:
                    raise ValueError(f"Final result ticket_id {result.ticket_id!r} does not match {ticket_id!r}")
                trajectory_path = logger.save(result=result.to_dict())
                return InvestigationRun(
                    model=self.client.model,
                    elapsed_ms=logger.elapsed_ms,
                    tokens=tokens,
                    outcome=result,
                    steps=steps,
                    trajectory_path=str(trajectory_path) if trajectory_path else None,
                )
            raise RuntimeError(f"Investigation exceeded the {max_turns}-turn limit without a final result")
        except Exception as error:
            logger.save(error=str(error))
            raise


def _parse_json_content(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise ValueError("Final model content was not a JSON object")
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("Final model content must be a JSON object")
    return value


def _as_token_count(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _record_evidence(evidence: dict[str, Any], name: str, arguments: dict[str, Any], result: Any, ticket_id: str) -> None:
    if not isinstance(result, dict) and name != "query_ledger":
        return
    if name == "get_ticket" and isinstance(result, dict) and result.get("id") == ticket_id:
        evidence["ticket"] = result
    elif name == "query_ledger" and arguments.get("ticket_id") == ticket_id:
        evidence["ledger"] = True
    elif name == "get_snapshot" and evidence["ticket"] and (
        arguments.get("sku") == evidence["ticket"].get("sku") and arguments.get("location") == evidence["ticket"].get("location")
    ):
        evidence["snapshot"] = True
    elif name == "get_document" and isinstance(result, dict) and result.get("id"):
        evidence["documents"].add(result["id"])


def _missing_evidence(evidence: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    ticket = evidence["ticket"]
    if ticket is None:
        return ["get_ticket(ticket_id)"]
    if not evidence["ledger"]:
        missing.append("query_ledger(ticket_id)")
    if not evidence["snapshot"]:
        missing.append("get_snapshot(ticket.sku, ticket.location)")
    for document_id in ticket.get("document_refs", []):
        if document_id not in evidence["documents"]:
            missing.append(f"get_document({document_id})")
    return missing


def _evidence_gate_complete(evidence: dict[str, Any]) -> bool:
    return evidence["ticket"] is not None and not _missing_evidence(evidence)
