from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from .agent import InvestigationRun, Investigator
from .context import compact_json, select_review_evidence
from .models import InvestigationResult, RESULT_SCHEMA
from .ollama import OllamaClient


DEFAULT_ROUTING_MODELS = ("qwen3:8b", "qwen3.5:27b")
DEEP_REVIEW_CODES = {"DUPLICATE_LEDGER_EVENT", "INSUFFICIENT_EVIDENCE"}
DEEP_REVIEW_FLAGS = {"missing_document", "duplicate_event", "conflicting_stock"}


@dataclass(frozen=True)
class RoutedInvestigationRun:
    model: str
    elapsed_ms: int
    tokens: dict[str, int]
    outcome: InvestigationResult
    steps: list[dict[str, Any]]
    trajectory_path: str | None
    routing: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "time": {
                "elapsed_ms": self.elapsed_ms,
                "elapsed_seconds": round(self.elapsed_ms / 1000, 3),
            },
            "tokens": self.tokens,
            "outcome": self.outcome.to_dict(),
            "routing": self.routing,
            "steps": self.steps,
            "trajectory_path": self.trajectory_path,
        }


class RoutedInvestigator:
    """Run a fast model first and escalate only when the result warrants it."""

    def __init__(
        self,
        models: tuple[str, ...] = DEFAULT_ROUTING_MODELS,
        host: str | None = None,
        instructions_path: Path | None = None,
        investigator_factory: Callable[[str], Investigator] | None = None,
    ) -> None:
        self.models = models
        self.host = host
        self.instructions_path = instructions_path
        self._investigator_factory = investigator_factory

    @property
    def model(self) -> str:
        return f"auto:{'->'.join(self.models)}"

    def investigate(self, ticket_id: str, max_turns: int = 12, trajectory_dir: Path | None = Path("trajectories")) -> InvestigationResult:
        return self.investigate_with_trace(ticket_id, max_turns, trajectory_dir).outcome

    def investigate_with_trace(
        self, ticket_id: str, max_turns: int = 12, trajectory_dir: Path | None = Path("trajectories")
    ) -> RoutedInvestigationRun:
        started = perf_counter()
        attempts: list[dict[str, Any]] = []
        successful_runs: list[InvestigationRun] = []
        next_reason = "initial fast pass"

        for index, model in enumerate(self.models):
            attempt_dir = trajectory_dir / _safe_name(model) if trajectory_dir is not None else None
            try:
                if index == 0 or self._investigator_factory is not None or not successful_runs:
                    run = self._make_investigator(model).investigate_with_trace(ticket_id, max_turns, attempt_dir)
                else:
                    run = self._review_evidence(
                        model, ticket_id, successful_runs[0], successful_runs, next_reason, attempt_dir
                    )
                successful_runs.append(run)
                evidence_flags = sorted(_combined_evidence_flags(successful_runs))
                attempts.append(
                    {
                        "model": model,
                        "reason": next_reason,
                        "status": "completed",
                        "elapsed_ms": run.elapsed_ms,
                        "tokens": run.tokens,
                        "root_cause_code": run.outcome.root_cause_code,
                        "confidence": run.outcome.confidence,
                        "requires_escalation": run.outcome.requires_escalation,
                        "evidence_flags": evidence_flags,
                        "trajectory_path": run.trajectory_path,
                        "error": None,
                    }
                )
                next_reason = _escalation_reason(index, successful_runs, len(self.models))
                if next_reason is None:
                    break
            except Exception as error:
                attempts.append(
                    {
                        "model": model,
                        "reason": next_reason,
                        "status": "error",
                        "elapsed_ms": None,
                        "tokens": {"prompt": 0, "completion": 0, "total": 0},
                        "root_cause_code": None,
                        "confidence": None,
                        "requires_escalation": None,
                        "evidence_flags": [],
                        "trajectory_path": None,
                        "error": str(error),
                    }
                )
                next_reason = f"{model} failed, so the next tier was attempted"

        if not successful_runs:
            errors = "; ".join(f"{attempt['model']}: {attempt['error']}" for attempt in attempts)
            raise RuntimeError(f"All routed models failed for {ticket_id}: {errors}")

        final_run = successful_runs[-1]
        tokens = {
            key: sum(run.tokens[key] for run in successful_runs)
            for key in ("prompt", "completion", "total")
        }
        elapsed_ms = round((perf_counter() - started) * 1000)
        steps = _combine_steps(attempts, successful_runs)
        routing = {
            "mode": "auto",
            "configured_models": list(self.models),
            "models_used": [attempt["model"] for attempt in attempts],
            "final_model": final_run.model,
            "attempt_count": len(attempts),
            "attempts": attempts,
        }
        trajectory_path = _save_routing_trajectory(
            trajectory_dir, ticket_id, elapsed_ms, tokens, final_run.outcome, routing
        )
        return RoutedInvestigationRun(
            model=final_run.model,
            elapsed_ms=elapsed_ms,
            tokens=tokens,
            outcome=final_run.outcome,
            steps=steps,
            trajectory_path=str(trajectory_path) if trajectory_path else None,
            routing=routing,
        )

    def _make_investigator(self, model: str) -> Investigator:
        if self._investigator_factory is not None:
            return self._investigator_factory(model)
        return Investigator(self._make_client(model), self.instructions_path)

    def _make_client(self, model: str) -> OllamaClient:
        if model.endswith(":8b"):
            max_output_tokens = 768
        else:
            max_output_tokens = 1024
        return OllamaClient(model=model, host=self.host, max_output_tokens=max_output_tokens)

    def _review_evidence(
        self,
        model: str,
        ticket_id: str,
        evidence_run: InvestigationRun,
        prior_runs: list[InvestigationRun],
        reason: str,
        output_dir: Path | None,
    ) -> InvestigationRun:
        instructions_path = self.instructions_path or Path(__file__).parents[2] / "instructions" / "investigator.md"
        instructions = instructions_path.read_text(encoding="utf-8")
        evidence = select_review_evidence(evidence_run.steps)
        review_payload = {
            "ticket_id": ticket_id,
            "routing_reason": reason,
            "evidence": evidence,
            "prior_outcomes": [run.outcome.to_dict() for run in prior_runs],
        }
        messages = [
            {
                "role": "system",
                "content": instructions
                + "\n\nYou are reviewing evidence already gathered by the primary model. Do not call tools. "
                "The evidence bundle is already filtered to ticket-relevant records. "
                "Independently reconcile the supplied evidence and return only the final JSON result. "
                "Prior outcomes are advisory and may be wrong.",
            },
            {"role": "user", "content": compact_json(review_payload)},
        ]
        started = perf_counter()
        response = self._make_client(model).chat(messages, [], RESULT_SCHEMA)
        elapsed_ms = round((perf_counter() - started) * 1000)
        message = response.get("message", {})
        public_content = _strip_thinking(message.get("content", ""))
        outcome = InvestigationResult.from_dict(_parse_review_json(public_content))
        if outcome.ticket_id != ticket_id:
            raise ValueError(f"Review result ticket_id {outcome.ticket_id!r} does not match {ticket_id!r}")
        tokens = {
            "prompt": _token_count(response.get("prompt_eval_count")),
            "completion": _token_count(response.get("eval_count")),
            "total": _token_count(response.get("prompt_eval_count")) + _token_count(response.get("eval_count")),
        }
        steps = [
            {
                "step": 1,
                "type": "review",
                "turn": 1,
                "elapsed_ms": elapsed_ms,
                "prompt_tokens": tokens["prompt"],
                "completion_tokens": tokens["completion"],
                "content": public_content,
                "tool_calls": [],
            }
        ]
        trajectory_path = _save_review_trajectory(
            output_dir, ticket_id, model, reason, elapsed_ms, tokens, outcome, evidence, prior_runs
        )
        return InvestigationRun(
            model=model,
            elapsed_ms=elapsed_ms,
            tokens=tokens,
            outcome=outcome,
            steps=steps,
            trajectory_path=str(trajectory_path) if trajectory_path else None,
        )


def _escalation_reason(index: int, runs: list[InvestigationRun], tier_count: int) -> str | None:
    if index >= tier_count - 1:
        return None
    current = runs[-1].outcome
    evidence_flags = _combined_evidence_flags(runs)
    deep_flags = sorted(evidence_flags & DEEP_REVIEW_FLAGS)
    if deep_flags:
        return f"evidence requires deep review: {', '.join(deep_flags)}"
    if current.root_cause_code in DEEP_REVIEW_CODES:
        return f"primary model returned high-review outcome {current.root_cause_code}"
    if current.requires_escalation:
        return "primary model requested escalation"
    if current.confidence < 0.8:
        return f"primary model confidence {current.confidence:.2f} was below 0.80"
    return None


def _evidence_flags(run: InvestigationRun) -> set[str]:
    flags: set[str] = set()
    ticket: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None
    documents: list[dict[str, Any]] = []
    ledger_events: list[dict[str, Any]] = []
    for step in run.steps:
        if step.get("type") != "tool":
            continue
        name = step.get("name")
        result = step.get("result")
        if name == "get_ticket" and isinstance(result, dict) and "error" not in result:
            ticket = result
        elif name == "get_snapshot" and isinstance(result, dict) and "error" not in result:
            snapshot = result
        elif name == "get_document" and isinstance(result, dict):
            if "error" in result:
                flags.add("missing_document")
            else:
                documents.append(result)
        elif name == "query_ledger" and isinstance(result, list):
            ledger_events.extend(event for event in result if isinstance(event, dict))

    if ticket and len(ticket.get("document_refs", [])) > 1:
        flags.add("multiple_documents")
    if any(document.get("status") == "partially_received" for document in documents):
        flags.add("partial_transfer")
    if any(event.get("state") == "failed" for event in ledger_events) or any(
        document.get("reservation_release_status") == "failed" for document in documents
    ):
        flags.add("failed_workflow")
    if any(event.get("state") == "pending_post" for event in ledger_events):
        flags.add("pending_post")
    if any(event.get("retry_of") for event in ledger_events) or _has_duplicate_effect(ledger_events):
        flags.add("duplicate_event")

    completed_transfer_ids = {
        document.get("id")
        for document in documents
        if document.get("type") == "transfer"
        and document.get("status") == "received"
        and ticket
        and document.get("sku") == ticket.get("sku")
        and document.get("destination_location") == ticket.get("location")
    }
    posted_receipt = any(
        event.get("event_type") == "transfer_received"
        and event.get("state") == "posted"
        and event.get("quantity_delta", 0) > 0
        and event.get("document_id") in completed_transfer_ids
        and ticket
        and event.get("sku") == ticket.get("sku")
        and event.get("location") == ticket.get("location")
        for event in ledger_events
    )
    if (
        ticket
        and snapshot
        and completed_transfer_ids
        and posted_receipt
        and ticket.get("expected_quantity") != snapshot.get("physical_quantity")
    ):
        flags.add("conflicting_stock")
    return flags


def _combined_evidence_flags(runs: list[InvestigationRun]) -> set[str]:
    flags: set[str] = set()
    for run in runs:
        flags.update(_evidence_flags(run))
    return flags


def _has_duplicate_effect(events: list[dict[str, Any]]) -> bool:
    seen: set[tuple[Any, ...]] = set()
    for event in events:
        if event.get("state") != "posted" or event.get("quantity_delta") in (None, 0):
            continue
        signature = (
            event.get("event_type"),
            event.get("document_id"),
            event.get("location"),
            event.get("quantity_delta"),
        )
        if signature in seen:
            return True
        seen.add(signature)
    return False


def _combine_steps(attempts: list[dict[str, Any]], successful_runs: list[InvestigationRun]) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    successful_by_model = {run.model: run for run in successful_runs}
    for attempt in attempts:
        combined.append(
            {
                "step": len(combined) + 1,
                "type": "routing",
                "model": attempt["model"],
                "reason": attempt["reason"],
                "status": attempt["status"],
                "error": attempt["error"],
            }
        )
        run = successful_by_model.get(attempt["model"])
        if run is None:
            continue
        for step in run.steps:
            combined.append({**step, "step": len(combined) + 1, "model": run.model})
    return combined


def _save_routing_trajectory(
    output_dir: Path | None,
    ticket_id: str,
    elapsed_ms: int,
    tokens: dict[str, int],
    outcome: InvestigationResult,
    routing: dict[str, Any],
) -> Path | None:
    if output_dir is None:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = output_dir / f"{ticket_id}_route_{timestamp}.json"
    payload = {
        "ticket_id": ticket_id,
        "elapsed_ms": elapsed_ms,
        "tokens": tokens,
        "outcome": outcome.to_dict(),
        "routing": routing,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _save_review_trajectory(
    output_dir: Path | None,
    ticket_id: str,
    model: str,
    reason: str,
    elapsed_ms: int,
    tokens: dict[str, int],
    outcome: InvestigationResult,
    evidence: list[dict[str, Any]],
    prior_runs: list[InvestigationRun],
) -> Path | None:
    if output_dir is None:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = output_dir / f"{ticket_id}_review_{timestamp}.json"
    payload = {
        "ticket_id": ticket_id,
        "model": model,
        "reason": reason,
        "elapsed_ms": elapsed_ms,
        "tokens": tokens,
        "evidence": evidence,
        "prior_outcomes": [run.outcome.to_dict() for run in prior_runs],
        "outcome": outcome.to_dict(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _parse_review_json(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise ValueError("Review model content was not JSON")
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("Review model content must be a JSON object")
    return value


def _strip_thinking(content: Any) -> Any:
    if isinstance(content, str) and "</think>" in content:
        return content.rsplit("</think>", 1)[1].strip()
    return content


def _token_count(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value)
