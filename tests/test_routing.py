import json

import pytest

from warehouse_investigator.agent import InvestigationRun
from warehouse_investigator.models import InvestigationResult
from warehouse_investigator.routing import RoutedInvestigator
from warehouse_investigator.tools import execute_tool


def make_run(
    model: str,
    code: str = "TRANSFER_NOT_RECEIVED",
    confidence: float = 0.95,
    escalation: bool = False,
) -> InvestigationRun:
    outcome = InvestigationResult(
        ticket_id="INC-001",
        root_cause_code=code,
        summary="Fixture result.",
        evidence_ids=["TR-100", "EV-1002"],
        recommended_action="Complete receiving.",
        confidence=confidence,
        requires_escalation=escalation,
    )
    return InvestigationRun(
        model=model,
        elapsed_ms=100,
        tokens={"prompt": 100, "completion": 20, "total": 120},
        outcome=outcome,
        steps=[{"step": 1, "type": "model"}],
        trajectory_path=None,
    )


class FakeInvestigator:
    def __init__(self, run: InvestigationRun) -> None:
        self.run = run

    def investigate_with_trace(self, *_args, **_kwargs) -> InvestigationRun:
        return self.run


def make_router(runs: dict[str, InvestigationRun], models: tuple[str, ...] | None = None) -> RoutedInvestigator:
    return RoutedInvestigator(
        models=models or tuple(runs),
        investigator_factory=lambda model: FakeInvestigator(runs[model]),
    )


def test_unknown_ticket_fails_fast_without_trying_any_tier() -> None:
    def _factory(_model: str):
        raise AssertionError("no tier should be constructed for an unknown ticket")

    router = RoutedInvestigator(investigator_factory=_factory)

    with pytest.raises(ValueError, match="No ticket found for 'INC-999'"):
        router.investigate_with_trace("INC-999", trajectory_dir=None)


def test_high_confidence_fast_result_stops_at_8b() -> None:
    router = make_router(
        {
            "qwen3:8b": make_run("qwen3:8b"),
            "qwen3.5:27b": make_run("qwen3.5:27b"),
        }
    )

    run = router.investigate_with_trace("INC-001", trajectory_dir=None)

    assert run.model == "qwen3:8b"
    assert run.routing["models_used"] == ["qwen3:8b"]
    assert run.tokens["total"] == 120


def test_low_primary_confidence_escalates_to_27b() -> None:
    router = make_router(
        {
            "qwen3:8b": make_run("qwen3:8b", confidence=0.7),
            "qwen3.5:27b": make_run("qwen3.5:27b", confidence=0.95),
        }
    )

    run = router.investigate_with_trace("INC-001", trajectory_dir=None)

    assert run.model == "qwen3.5:27b"
    assert run.routing["models_used"] == ["qwen3:8b", "qwen3.5:27b"]
    assert run.tokens["total"] == 240


def test_high_risk_outcome_receives_deep_review() -> None:
    router = make_router(
        {
            model: make_run(model, code="DUPLICATE_LEDGER_EVENT", escalation=True)
            for model in ("qwen3:8b", "qwen3.5:27b")
        }
    )

    run = router.investigate_with_trace("INC-001", trajectory_dir=None)

    assert run.model == "qwen3.5:27b"
    assert run.routing["models_used"] == ["qwen3:8b", "qwen3.5:27b"]


def test_missing_document_is_finalized_without_deep_review() -> None:
    runs = {model: make_run(model) for model in ("qwen3:8b", "qwen3.5:27b")}
    for run in runs.values():
        run.steps.append(
            {
                "step": 2,
                "type": "tool",
                "name": "get_document",
                "result": {"error": "No document found"},
            }
        )
    router = make_router(runs)

    run = router.investigate_with_trace("INC-001", trajectory_dir=None)

    assert run.model == "qwen3:8b"
    assert run.outcome.root_cause_code == "INSUFFICIENT_EVIDENCE"
    assert run.routing["attempts"][0]["evidence_flags"] == ["missing_document"]
    assert run.routing["models_used"] == ["qwen3:8b"]


def test_pending_post_is_finalized_without_deep_review() -> None:
    runs = {model: make_run(model) for model in ("qwen3:8b", "qwen3.5:27b")}
    for run in runs.values():
        run.steps.append(
            {
                "step": 2,
                "type": "tool",
                "name": "query_ledger",
                "result": [
                    {
                        "id": "EV-10002",
                        "event_type": "count_adjustment",
                        "state": "pending_post",
                        "document_id": "CC-302",
                    }
                ],
            }
        )
    router = make_router(runs)

    run = router.investigate_with_trace("INC-001", trajectory_dir=None)

    assert run.model == "qwen3:8b"
    assert run.outcome.root_cause_code == "COUNT_ADJUSTMENT_NOT_POSTED"
    assert run.routing["attempts"][0]["evidence_flags"] == ["pending_post"]


def test_partial_transfer_is_finalized_without_deep_review() -> None:
    runs = {model: make_run(model) for model in ("qwen3:8b", "qwen3.5:27b")}
    for run in runs.values():
        run.steps.append(
            {
                "step": 2,
                "type": "tool",
                "name": "get_document",
                "result": {"id": "TR-200", "type": "transfer", "status": "partially_received"},
            }
        )
    router = make_router(runs)

    run = router.investigate_with_trace("INC-001", trajectory_dir=None)

    assert run.model == "qwen3:8b"
    assert run.outcome.root_cause_code == "PARTIAL_TRANSFER_RECEIPT"
    assert run.routing["attempts"][0]["evidence_flags"] == ["partial_transfer"]


def test_posted_release_is_finalized_without_deep_review() -> None:
    runs = {
        model: make_run(model, code="STALE_RESERVATION")
        for model in ("qwen3:8b", "qwen3.5:27b")
    }
    for run in runs.values():
        run.steps.extend(
            [
                {
                    "step": 2,
                    "type": "tool",
                    "name": "query_ledger",
                    "result": [
                        {
                            "id": "EV-7003",
                            "event_type": "reservation_released",
                            "state": "posted",
                        }
                    ],
                },
                {
                    "step": 3,
                    "type": "tool",
                    "name": "get_snapshot",
                    "result": {"reserved_quantity": 0, "physical_quantity": 50},
                },
            ]
        )
    router = make_router(runs)

    run = router.investigate_with_trace("INC-001", trajectory_dir=None)

    assert run.model == "qwen3:8b"
    assert run.outcome.root_cause_code == "NO_DISCREPANCY"
    assert "posted_release" in run.routing["attempts"][0]["evidence_flags"]


def test_failed_release_with_remaining_reserved_does_not_force_review() -> None:
    runs = {
        model: make_run(model, code="STALE_RESERVATION")
        for model in ("qwen3:8b", "qwen3.5:27b")
    }
    for run in runs.values():
        run.steps.extend(
            [
                {
                    "step": 2,
                    "type": "tool",
                    "name": "query_ledger",
                    "result": [
                        {
                            "id": "EV-8003",
                            "event_type": "reservation_released",
                            "state": "failed",
                        }
                    ],
                },
                {
                    "step": 3,
                    "type": "tool",
                    "name": "get_snapshot",
                    "result": {"reserved_quantity": 9, "physical_quantity": 50},
                },
            ]
        )
    router = make_router(runs)

    run = router.investigate_with_trace("INC-001", trajectory_dir=None)

    assert run.model == "qwen3:8b"
    assert "posted_release" not in run.routing["attempts"][0]["evidence_flags"]


class ReviewClient:
    model = "qwen3.5:27b"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def chat(self, messages, tools, response_format):
        self.calls.append({"messages": messages, "tools": tools, "format": response_format})
        return {
            "message": {
                "role": "assistant",
                "content": '{"ticket_id":"INC-001","root_cause_code":"TRANSFER_NOT_RECEIVED","summary":"Receipt is still pending.","evidence_ids":["TR-100","EV-1002"],"recommended_action":"Complete receiving.","confidence":0.9,"requires_escalation":false}',
            },
            "prompt_eval_count": 50,
            "eval_count": 10,
        }


class ReviewRouter(RoutedInvestigator):
    def __init__(self, primary_run: InvestigationRun, client: ReviewClient) -> None:
        super().__init__(models=("qwen3:8b", "qwen3.5:27b"))
        self._primary_run = primary_run
        self._client = client

    def _make_investigator(self, model: str) -> FakeInvestigator:
        return FakeInvestigator(self._primary_run)

    def _make_client(self, model: str) -> ReviewClient:
        return self._client


def test_deep_review_receives_filtered_ticket_evidence() -> None:
    ticket = execute_tool("get_ticket", {"ticket_id": "INC-001"})
    ledger = execute_tool("query_ledger", {"ticket_id": "INC-001"})
    snapshot = execute_tool("get_snapshot", {"sku": "SKU-RED-CHAIR", "location": "SEA-01"})
    primary = make_run("qwen3:8b", confidence=0.7)
    primary.steps.extend(
        [
            {"type": "tool", "name": "get_ticket", "arguments": {"ticket_id": "INC-001"}, "result": ticket},
            {"type": "tool", "name": "query_ledger", "arguments": {"ticket_id": "INC-001"}, "result": ledger},
            {
                "type": "tool",
                "name": "get_snapshot",
                "arguments": {"sku": "SKU-RED-CHAIR", "location": "SEA-01"},
                "result": snapshot,
            },
            {"type": "tool", "name": "get_document", "arguments": {"document_id": "TR-100"}, "result": {"id": "TR-100"}},
            {
                "type": "tool",
                "name": "get_document",
                "arguments": {"document_id": "TR-X001"},
                "result": {"id": "TR-X001", "sku": "SKU-NOISE-001"},
            },
        ]
    )
    client = ReviewClient()
    router = ReviewRouter(primary, client)

    run = router.investigate_with_trace("INC-001", trajectory_dir=None)
    payload = json.loads(client.calls[0]["messages"][1]["content"])
    ledger_ids = [event["id"] for item in payload["evidence"] if item["tool"] == "query_ledger" for event in item["result"]]
    document_ids = [item["arguments"]["document_id"] for item in payload["evidence"] if item["tool"] == "get_document"]

    assert run.model == "qwen3.5:27b"
    assert "EV-1001" in ledger_ids
    assert "EV-1002" in ledger_ids
    assert "EV-X001" not in ledger_ids
    assert "EV-H001A" not in ledger_ids
    assert document_ids == ["TR-100"]
    assert "already filtered" in client.calls[0]["messages"][0]["content"]


def test_deep_review_client_uses_extended_timeout() -> None:
    router = RoutedInvestigator()

    assert router._make_client("qwen3:8b").timeout_seconds == 180
    assert router._make_client("qwen3.5:27b").timeout_seconds == 300


class TimeoutThenSuccessClient(ReviewClient):
    def __init__(self) -> None:
        super().__init__()
        self.chat_calls = 0

    def chat(self, messages, tools, response_format):
        self.chat_calls += 1
        if self.chat_calls == 1:
            raise TimeoutError("timed out")
        return super().chat(messages, tools, response_format)


class AlwaysTimeoutClient(ReviewClient):
    def __init__(self) -> None:
        super().__init__()
        self.chat_calls = 0

    def chat(self, messages, tools, response_format):
        self.chat_calls += 1
        raise TimeoutError("timed out")


def test_deep_review_retries_once_after_timeout() -> None:
    primary = make_run("qwen3:8b", confidence=0.7)
    client = TimeoutThenSuccessClient()
    router = ReviewRouter(primary, client)

    run = router.investigate_with_trace("INC-001", trajectory_dir=None)

    assert client.chat_calls == 2
    assert run.model == "qwen3.5:27b"
    assert run.routing["attempts"][-1]["status"] == "completed"


def test_deep_review_falls_back_after_retry_timeout() -> None:
    primary = make_run("qwen3:8b", confidence=0.7)
    client = AlwaysTimeoutClient()
    router = ReviewRouter(primary, client)

    run = router.investigate_with_trace("INC-001", trajectory_dir=None)

    assert client.chat_calls == 2
    assert run.model == "qwen3:8b"
    assert run.routing["attempts"][-1]["status"] == "error"
    assert "timed out" in run.routing["attempts"][-1]["error"]
