from warehouse_investigator.agent import InvestigationRun
from warehouse_investigator.models import InvestigationResult
from warehouse_investigator.routing import RoutedInvestigator


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


def test_missing_document_overrides_high_model_confidence() -> None:
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

    assert run.model == "qwen3.5:27b"
    assert run.routing["attempts"][0]["evidence_flags"] == ["missing_document"]
