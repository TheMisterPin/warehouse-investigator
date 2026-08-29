# Warehouse Investigator

A small, local-first warehouse incident investigator. A Python runner sends an incident to Ollama, lets the model call read-only warehouse tools, validates a structured diagnosis, and saves a complete trajectory for review.

## What is included

- `investigate`: CLI for one incident
- automatic local-model routing with a fast primary and deep-review tier
- local Ollama chat client with tool calling and JSON-schema final output
- read-only tools over deterministic sample warehouse data
- validated `InvestigationResult` contract
- JSON trajectory logs with model turns, tool calls, tool results, and timings
- 12-case safety-aware evaluation harness

## Setup

Requires Python 3.11+ and a running [Ollama](https://ollama.com/) instance.

```bash
cd /Users/michele/Dev/Projects/LocalAI/warehouse-investigator
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ollama pull qwen3:8b
ollama pull qwen3.5:27b
```

Normal runs use `qwen3:8b` first and ask `qwen3.5:27b` to review only uncertain, conflicting, or high-risk evidence. Local testing found 8B faster and more reliable for tool use than the installed 4B model, so 4B is not part of the supported automatic route.

## Run an investigation

```bash
investigate INC-001
```

Or, without installing the command:

```bash
PYTHONPATH=src python -m warehouse_investigator INC-001
```

Useful options:

```bash
investigate INC-001 --model qwen3:8b
investigate INC-001 --primary-model qwen3:8b --deep-model qwen3.5:27b
investigate INC-001 --no-log
```

Each run writes a JSON trajectory under `trajectories/` unless `--no-log` is used.
The CLI also prints a complete run record with the final model, elapsed time, aggregate prompt/completion token counts, final outcome, routing reasons, and each observable model/tool step. Higher model tiers reuse the evidence gathered by the primary model rather than repeating tool calls.

### Model routing

| Mode | Route | Intended use |
| --- | --- | --- |
| Automatic (default) | `qwen3:8b` → `qwen3.5:27b` when needed | Lowest measured time-to-answer with deep review for risk and ambiguity |
| Fixed model | `--model <name>` | Reproducible model comparisons and evaluation baselines |

Auto routing escalates on objective evidence complexity, low confidence, explicit escalation, or high-review outcomes such as duplicate ledger events and insufficient evidence.

## Evaluate the fixed cases

```bash
evaluate --runs 1
evaluate --case INC-012
evaluate --model qwen3.5:27b --case INC-012
```

This runs the 12-case challenge and writes a JSON report under `reports/`. Use `--runs` for repetition and `--case` for targeted reruns. A run passes only when its ticket ID, root-cause code, required and forbidden evidence, recommended-action relevance and safety, confidence, and escalation behavior all meet the case definition. The report includes per-run trajectories plus aggregate accuracy, latency, and token usage. It requires Ollama and a pulled model.

## Project layout

```text
instructions/                 Investigator operating procedure
src/warehouse_investigator/data/warehouse/  Separated model-visible operational records
src/warehouse_investigator/data/evaluation/ Evaluator-only ground truth
src/warehouse_investigator/   Runtime, data tools, CLI, and evaluator
tests/                        Fast checks that need no model runtime
```

The warehouse data is deliberately deterministic but no longer case-shaped: tickets, ledger events, documents, and snapshot history live in separate datasets with distractor activity. Replace `warehouse_data.py` with database adapters later; the agent contract and tool interface stay the same. Evaluation labels are stored separately and are never returned by model tools.

## Development notes

The decisions, live-run result, evidence-gate change, and next milestones for the initial implementation are captured in [docs/first-pass-development.md](docs/first-pass-development.md).

The repeatable 9-run baseline, stricter scoring contract, measured latency/token usage, and next evaluation expansion are captured in [docs/baseline-evaluation.md](docs/baseline-evaluation.md).

The implementation changes and decisions for the second development pass are captured in [docs/second-pass-development.md](docs/second-pass-development.md).

The 12-case data-driven challenge, safety checks, expanded run, evaluator calibration, and targeted rerun are captured in [docs/third-pass-development.md](docs/third-pass-development.md).

The measured model-routing policy, escalation triggers, evidence reuse, and representative benchmarks are captured in [docs/model-routing.md](docs/model-routing.md).

The decision to retire the 4B economy tier and standardize the supported route on 8B with selective 27B review is captured in [docs/fourth-pass-development.md](docs/fourth-pass-development.md).

The separated operational datasets, buried-evidence challenge, and resulting 5/12 strict versus 11/12 diagnostic baseline are captured in [docs/fifth-pass-development.md](docs/fifth-pass-development.md).
