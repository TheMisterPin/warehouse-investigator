# Warehouse Investigator

A small, local-first warehouse incident investigator. A Python runner sends an incident to Ollama, lets the model call read-only warehouse tools, validates a structured diagnosis, and saves a complete trajectory for review.

## What is included

- `investigate`: CLI for one incident
- local Ollama chat client with tool calling and JSON-schema final output
- read-only tools over deterministic sample warehouse data
- validated `InvestigationResult` contract
- JSON trajectory logs with model turns, tool calls, tool results, and timings
- small fixed-case evaluator

## Setup

Requires Python 3.11+ and a running [Ollama](https://ollama.com/) instance.

```bash
cd /Users/michele/Dev/Projects/LocalAI/warehouse-investigator
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
ollama pull qwen3-coder:30b
```

The runner uses `qwen3-coder:30b` by default. Change it with `--model` or `OLLAMA_MODEL`.

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
investigate INC-001 --model qwen3-coder:30b --max-turns 12
investigate INC-001 --no-log
```

Each run writes a JSON trajectory under `trajectories/` unless `--no-log` is used.
The CLI also prints a complete run record with the model, elapsed time, Ollama prompt/completion token counts, final outcome, and each model/tool step. Model thinking is disabled so the trace records observable actions and evidence rather than a hidden-reasoning transcript.

## Evaluate the fixed cases

```bash
evaluate
```

This runs each fixture through the agent and compares its `root_cause_code` to the expected code. It requires Ollama and a pulled model.

## Project layout

```text
instructions/                 Investigator operating procedure
src/warehouse_investigator/   Runtime, data tools, CLI, and evaluator
tests/                        Fast checks that need no model runtime
```

The warehouse data is deliberately a small deterministic fixture. Replace `sample_data.py` with a database adapter later; the agent contract and tool interface stay the same.

## Development notes

The decisions, live-run result, evidence-gate change, and next milestones for the initial implementation are captured in [docs/first-pass-development.md](docs/first-pass-development.md).
