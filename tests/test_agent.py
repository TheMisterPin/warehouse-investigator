from pathlib import Path

from warehouse_investigator.agent import Investigator
from warehouse_investigator.context import ALREADY_FETCHED
from warehouse_investigator.models import RESULT_SCHEMA
from warehouse_investigator.tools import TOOL_DEFINITIONS


class RecordingClient:
    model = "stub-model"

    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, messages, tools, response_format):
        self.calls.append({"messages": messages, "tools": tools, "format": response_format})
        return self.responses.pop(0)


def _tool_response(*calls: dict) -> dict:
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": call} for call in calls],
        },
        "prompt_eval_count": 10,
        "eval_count": 4,
    }


def _final_response() -> dict:
    return {
        "message": {
            "role": "assistant",
            "content": '{"ticket_id":"INC-001","root_cause_code":"TRANSFER_NOT_RECEIVED","summary":"Transfer is in transit.","evidence_ids":["TR-100"],"recommended_action":"Receive transfer.","confidence":0.9,"requires_escalation":false}',
        },
        "prompt_eval_count": 20,
        "eval_count": 8,
    }


class StubClient:
    model = "stub-model"

    def __init__(self) -> None:
        self.responses = [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "get_ticket", "arguments": {"ticket_id": "INC-001"}}}],
                },
                "prompt_eval_count": 100,
                "eval_count": 8,
            },
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "query_ledger", "arguments": {"ticket_id": "INC-001"}}},
                        {"function": {"name": "get_snapshot", "arguments": {"sku": "SKU-RED-CHAIR", "location": "SEA-01"}}},
                        {"function": {"name": "get_document", "arguments": {"document_id": "TR-100"}}},
                    ],
                },
                "prompt_eval_count": 150,
                "eval_count": 30,
            },
            {
                "message": {
                    "role": "assistant",
                    "content": '{"ticket_id":"INC-001","root_cause_code":"TRANSFER_NOT_RECEIVED","summary":"Transfer is in transit.","evidence_ids":["TR-100"],"recommended_action":"Receive transfer.","confidence":0.9,"requires_escalation":false}',
                },
                "prompt_eval_count": 200,
                "eval_count": 40,
            },
        ]

    def chat(self, *_args, **_kwargs):
        return self.responses.pop(0)


def test_trace_contains_usage_outcome_and_tool_steps(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[1]
    investigator = Investigator(StubClient(), project_root / "instructions" / "investigator.md")
    run = investigator.investigate_with_trace("INC-001", trajectory_dir=tmp_path)

    assert run.tokens == {"prompt": 450, "completion": 78, "total": 528}
    assert run.outcome.root_cause_code == "TRANSFER_NOT_RECEIVED"
    assert [step["type"] for step in run.steps] == ["model", "tool", "model", "tool", "tool", "tool", "model"]
    assert run.trajectory_path is not None


def test_disables_tools_after_evidence_gate_completes(tmp_path: Path) -> None:
    client = RecordingClient(
        [
            _tool_response({"name": "get_ticket", "arguments": {"ticket_id": "INC-001"}}),
            _tool_response(
                {"name": "query_ledger", "arguments": {"ticket_id": "INC-001"}},
                {"name": "get_snapshot", "arguments": {"sku": "SKU-RED-CHAIR", "location": "SEA-01"}},
                {"name": "get_document", "arguments": {"document_id": "TR-100"}},
            ),
            _final_response(),
        ]
    )
    investigator = Investigator(client, Path(__file__).parents[1] / "instructions" / "investigator.md")

    investigator.investigate_with_trace("INC-001", trajectory_dir=tmp_path)

    assert client.calls[0]["tools"] == TOOL_DEFINITIONS
    assert client.calls[0]["format"] is None
    assert client.calls[-1]["tools"] == []
    assert client.calls[-1]["format"] == RESULT_SCHEMA


def test_duplicate_tool_call_returns_stub_instead_of_refetching(tmp_path: Path) -> None:
    client = RecordingClient(
        [
            _tool_response({"name": "get_ticket", "arguments": {"ticket_id": "INC-001"}}),
            _tool_response({"name": "get_ticket", "arguments": {"ticket_id": "INC-001"}}),
            _tool_response(
                {"name": "query_ledger", "arguments": {"ticket_id": "INC-001"}},
                {"name": "get_snapshot", "arguments": {"sku": "SKU-RED-CHAIR", "location": "SEA-01"}},
                {"name": "get_document", "arguments": {"document_id": "TR-100"}},
            ),
            _final_response(),
        ]
    )
    investigator = Investigator(client, Path(__file__).parents[1] / "instructions" / "investigator.md")

    run = investigator.investigate_with_trace("INC-001", trajectory_dir=tmp_path)
    ticket_results = [step["result"] for step in run.steps if step.get("name") == "get_ticket"]

    assert ticket_results[0]["id"] == "INC-001"
    assert ticket_results[1] == ALREADY_FETCHED


def test_does_not_stack_evidence_gate_user_nags(tmp_path: Path) -> None:
    client = RecordingClient(
        [
            _tool_response({"name": "get_ticket", "arguments": {"ticket_id": "INC-001"}}),
            {"message": {"role": "assistant", "content": "I am ready to diagnose."}, "prompt_eval_count": 10, "eval_count": 4},
            _tool_response(
                {"name": "query_ledger", "arguments": {"ticket_id": "INC-001"}},
                {"name": "get_snapshot", "arguments": {"sku": "SKU-RED-CHAIR", "location": "SEA-01"}},
                {"name": "get_document", "arguments": {"document_id": "TR-100"}},
            ),
            _final_response(),
        ]
    )
    investigator = Investigator(client, Path(__file__).parents[1] / "instructions" / "investigator.md")

    investigator.investigate_with_trace("INC-001", trajectory_dir=tmp_path)
    nag_count = sum(
        "Evidence gate is incomplete" in message.get("content", "")
        for call in client.calls
        for message in call["messages"]
    )

    assert nag_count == 0
    assert any(
        '"complete":false' in message.get("content", "") or '"complete": false' in message.get("content", "")
        for message in client.calls[2]["messages"]
    )
