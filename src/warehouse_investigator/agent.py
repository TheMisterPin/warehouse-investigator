from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .context import (
    ALREADY_FETCHED,
    already_fetched,
    build_model_messages,
    evidence_gate_complete,
    missing_evidence,
    new_evidence,
    record_evidence,
)
from .finalize import finalize_outcome
from .feedback import build_feedback_context
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

    @property
    def model(self) -> str:
        return self.client.model

    def investigate(self, ticket_id: str, max_turns: int = 12, trajectory_dir: Path | None = Path("trajectories")) -> InvestigationResult:
        return self.investigate_with_trace(ticket_id, max_turns, trajectory_dir).outcome

    def investigate_with_trace(
        self, ticket_id: str, max_turns: int = 12, trajectory_dir: Path | None = Path("trajectories")
    ) -> InvestigationRun:
        instructions = self.instructions_path.read_text(encoding="utf-8")
        logger = TrajectoryLogger(ticket_id, trajectory_dir)
        logger.add("run_started", model=self.client.model, max_turns=max_turns)
        tokens = {"prompt": 0, "completion": 0, "total": 0}
        steps: list[dict[str, Any]] = []
        evidence = new_evidence()
        reviewed_feedback = build_feedback_context(ticket_id)
        if reviewed_feedback:
            logger.add("feedback_context", feedback=reviewed_feedback)
            steps.append({"step": len(steps) + 1, "type": "feedback", "feedback": reviewed_feedback})
        try:
            for turn in range(1, max_turns + 1):
                gate_complete = evidence_gate_complete(evidence)
                tools = [] if gate_complete else TOOL_DEFINITIONS
                response_format = RESULT_SCHEMA if gate_complete else None
                messages = build_model_messages(ticket_id, instructions, evidence, reviewed_feedback)
                response = self.client.chat(messages, tools, response_format)
                message = response.get("message", {})
                observable_message = _observable_message(message, final_result_allowed=response_format is not None)
                prompt_tokens = _as_token_count(response.get("prompt_eval_count"))
                completion_tokens = _as_token_count(response.get("eval_count"))
                tokens["prompt"] += prompt_tokens
                tokens["completion"] += completion_tokens
                tokens["total"] += prompt_tokens + completion_tokens
                logger.add(
                    "model_response",
                    turn=turn,
                    message=observable_message,
                    done_reason=response.get("done_reason"),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
                tool_calls = message.get("tool_calls") or []
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "type": "model",
                        "turn": turn,
                        "elapsed_ms": logger.elapsed_ms,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "content": observable_message.get("content", ""),
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
                        if already_fetched(evidence, name, arguments):
                            result = ALREADY_FETCHED
                        else:
                            result = execute_tool(name, arguments)
                            record_evidence(evidence, name, arguments, result, ticket_id)
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
                    continue
                if not evidence_gate_complete(evidence):
                    missing = missing_evidence(evidence)
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
                    continue
                result = InvestigationResult.from_dict(_parse_json_content(message.get("content", "")))
                if result.ticket_id != ticket_id:
                    raise ValueError(f"Final result ticket_id {result.ticket_id!r} does not match {ticket_id!r}")
                outcome, pinned, reasons = finalize_outcome(result, steps)
                if pinned or reasons:
                    logger.add("verifier_adjustment", pinned=pinned, reasons=reasons, outcome=outcome.to_dict())
                    steps.append({"step": len(steps) + 1, "type": "verifier", "pinned": pinned, "reasons": reasons})
                run = InvestigationRun(
                    model=self.client.model,
                    elapsed_ms=logger.elapsed_ms,
                    tokens=tokens,
                    outcome=outcome,
                    steps=steps,
                    trajectory_path=None,
                )
                trajectory_path = logger.save(result=run.outcome.to_dict())
                return replace(run, trajectory_path=str(trajectory_path) if trajectory_path else None)
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


def _observable_message(message: dict[str, Any], final_result_allowed: bool) -> dict[str, Any]:
    observable = {key: value for key, value in message.items() if key != "thinking"}
    content = observable.get("content", "")
    if isinstance(content, str) and "</think>" in content:
        content = content.rsplit("</think>", 1)[1].strip()
    if observable.get("tool_calls"):
        names = [call.get("function", {}).get("name", "unknown") for call in observable["tool_calls"]]
        content = f"Requested tool call(s): {', '.join(names)}"
    elif not final_result_allowed:
        content = "No tool call produced; the evidence gate requested the remaining tools."
    observable["content"] = content
    return observable
