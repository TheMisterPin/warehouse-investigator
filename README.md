# Warehouse Investigator

A small, local-first warehouse incident investigator. A Python runner sends an incident to Ollama, lets the model call read-only warehouse tools, validates a structured diagnosis, and saves a complete trajectory for review.

## What is included

- `investigate`: CLI for one incident
- automatic local-model routing with a fast primary and deep-review tier
- local Ollama chat client with tool calling and JSON-schema final output
- read-only tools over a SQLite warehouse database and a Chroma index seeded from deterministic sample data
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
python -m warehouse_investigator.seed
ollama pull nomic-embed-text
ollama pull qwen3:8b
ollama pull qwen3.5:27b
```

`python -m warehouse_investigator.seed` creates `warehouse.db` and a `chroma/` index at the project root from the JSON datasets. SQLite tools also seed the database automatically if it is missing; `search_records` builds the Chroma index on first use if it is empty. Embeddings use Ollama (`nomic-embed-text` by default). Evaluation labels stay in JSON and are never written to the database or the index.

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
The CLI also prints a complete run record with the final model, elapsed time, aggregate prompt/completion token counts, final outcome, routing reasons, and each observable model/tool step. The primary model sees a compact evidence bundle on each turn. Higher model tiers reuse ticket-relevant evidence rather than repeating tool calls or receiving buried distractors.

### Model routing

| Mode | Route | Intended use |
| --- | --- | --- |
| Automatic (default) | `qwen3:8b` → `qwen3.5:27b` when needed | Lowest measured time-to-answer with deep review for risk and ambiguity |
| Fixed model | `--model <name>` | Reproducible model comparisons and evaluation baselines |

Auto routing applies a runtime finalizer to citations and procedure-implied causes, then escalates to 27B only for remaining risk such as duplicate ledger events, low confidence, or unpinned insufficient evidence.

## Evaluate the fixed cases

```bash
evaluate --runs 1
evaluate --case INC-012
evaluate --model qwen3.5:27b --case INC-012
evaluate --workers 2
```

This runs the 12-case challenge one ticket at a time and writes a JSON report under `reports/`. Use `--runs` for repetition, `--case` for targeted reruns, and `--workers` to change concurrency (default 1, so a local 27B review does not share the GPU). A run passes only when its ticket ID, root-cause code, required and forbidden evidence, recommended-action relevance and safety, confidence, and escalation behavior all meet the case definition. The report includes per-run trajectories plus aggregate accuracy, latency, and token usage. It requires Ollama and a pulled model.

## Project layout

```text
instructions/                 Investigator operating procedure
warehouse.db                  Generated SQLite warehouse (project root; gitignored)
chroma/                       Generated Chroma index (project root; gitignored)
src/warehouse_investigator/data/warehouse/  Source operational JSON used by seed
src/warehouse_investigator/data/evaluation/ Evaluator-only ground truth
src/warehouse_investigator/   Runtime, SQLite adapters, CLI, and evaluator
tests/                        Fast checks that need no model runtime
```

The warehouse data is deliberately deterministic but no longer case-shaped: tickets, ledger events, documents, and snapshot history live in separate JSON datasets with distractor activity. `warehouse_data.seed()` loads those records into `warehouse.db` at the project root, `index.seed_index()` embeds them into `chroma/` with Ollama, and the tools query both. `search_records` is optional semantic retrieval; exact lookups remain the evidence gate. Evaluation labels are stored separately and are never returned by model tools.

## Development notes

The decisions, live-run result, evidence-gate change, and next milestones for the initial implementation are captured in [docs/01-first-pass-development.md](docs/01-first-pass-development.md).

The repeatable 9-run baseline, stricter scoring contract, measured latency/token usage, and next evaluation expansion are captured in [docs/02-baseline-evaluation.md](docs/02-baseline-evaluation.md).

The implementation changes and decisions for the second development pass are captured in [docs/02-second-pass-development.md](docs/02-second-pass-development.md).

The 12-case data-driven challenge, safety checks, expanded run, evaluator calibration, and targeted rerun are captured in [docs/03-third-pass-development.md](docs/03-third-pass-development.md).

The measured model-routing policy, escalation triggers, evidence reuse, and representative benchmarks are captured in [docs/03a-model-routing.md](docs/03a-model-routing.md).

The decision to retire the 4B economy tier and standardize the supported route on 8B with selective 27B review is captured in [docs/04-fourth-pass-development.md](docs/04-fourth-pass-development.md).

The separated operational datasets, buried-evidence challenge, and resulting 5/12 strict versus 11/12 diagnostic baseline are captured in [docs/05-fifth-pass-development.md](docs/05-fifth-pass-development.md).

The compact evidence bundle, shortened evidence-gate prompt, filtered 27B review payload, and four-wide concurrent evaluation are captured in [docs/06-sixth-pass-development.md](docs/06-sixth-pass-development.md).

The SQLite warehouse adapters, Ollama/Chroma embeddings, and additive `search_records` tool are captured in [docs/07-seventh-pass-development.md](docs/07-seventh-pass-development.md).

The reliability work, ticket-scoped ledger, runtime finalizer, and 12/12 routed eval are captured in [docs/08-eighth-pass-development.md](docs/08-eighth-pass-development.md).

The reviewed feedback loop, verifier hardening, and evaluator regression export are captured in [docs/09-ninth-pass-development.md](docs/09-ninth-pass-development.md).
