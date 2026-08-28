from pathlib import Path

from warehouse_investigator.agent import Investigator


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
