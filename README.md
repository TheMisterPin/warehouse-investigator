# Warehouse Investigator

A small, local-first warehouse incident investigator. A Python runner sends an incident to Ollama, lets the model call read-only warehouse tools, validates a structured diagnosis, and saves a complete trajectory for review.

## Problem & User Value

**Who has this problem:** warehouse and inventory operations analysts working the exception queue in a WMS — the people who get tickets like "SEA-01 is short 6 units on SKU X" with no diagnosis attached, just a symptom.

**What bottleneck makes it worth solving:** closing one ticket means manually cross-referencing four sources — the ticket, a ledger that includes unrelated and historical noise, any referenced documents, and a stock snapshot plus its history — while reasoning about *state*, not just presence. A shipped transfer only affects the source location until receipt posts; a cancelled order can still leave a stale reservation; a count can be approved but not yet posted. Miss one distinction and an analyst either tells someone to re-post something that's actually a duplicate, or escalates something that was a one-click fix. At ticket volume, that inconsistency — not any single wrong answer — is the real cost.

**Does the agent solve it well:** given a ticket ID, the investigator retrieves and reconciles the same four sources, returns one of eight defined root-cause codes with cited evidence IDs, a concrete recommended action, a calibrated confidence score, and an explicit escalation flag. A runtime evidence gate refuses to let it guess before gathering that evidence. See [Improvement Changelog](#improvement-changelog) below for how well, measured.

**Can another person reproduce the result:** yes — every run and evaluation case is scored against fixed evidence and safety expectations rather than eyeballed. See Setup and Evaluate below.

*Ask yourself: who experiences the bottleneck, and why does solving it matter? Here, it's the analyst under ticket-volume pressure — the cost of inconsistency compounds across every ticket they close, not just the hard ones.*

## What is included

- `investigate`: CLI for one incident or a queue of them, printing a human-readable incident note by default (full JSON on request)
- automatic local-model routing with a fast primary and deep-review tier
- local Ollama chat client with tool calling and JSON-schema final output
- read-only tools over a SQLite warehouse database and a Chroma index seeded from deterministic sample data
- validated `InvestigationResult` contract
- JSON trajectory logs with model turns, tool calls, tool results, and timings
- 12-case safety-aware evaluation harness

## Setup

Requires Python 3.11+ and a running [Ollama](https://ollama.com/) instance.

```bash
git clone <this-repository-url>
cd warehouse-investigator
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

By default the CLI prints a short incident note — diagnosis, cited evidence, recommended action, confidence, and escalation — the kind of thing an analyst could paste straight into a ticket. Pass more than one ticket ID to work a queue instead of one incident:

```bash
investigate INC-001 INC-002 INC-003
```

This prints a one-line-per-ticket summary table instead, and a bad ticket ID among the batch shows as a failed row rather than aborting the run.

Useful options:

```bash
investigate INC-001 --model qwen3:8b
investigate INC-001 --primary-model qwen3:8b --deep-model qwen3.5:27b
investigate INC-001 --no-log
investigate INC-001 --format json   # full run record: model, timing, tokens, routing reasons, every observable step
```

Each run writes a JSON trajectory under `trajectories/` unless `--no-log` is used. `--format json` prints the complete run record instead of the incident note — the same shape saved to the trajectory, useful for scripting or for inspecting routing decisions. The primary model sees a compact evidence bundle on each turn. Higher model tiers reuse ticket-relevant evidence rather than repeating tool calls or receiving buried distractors. An unknown ticket ID fails immediately with a clear message instead of exhausting the turn budget.

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
trajectories/samples/         Committed example trajectories (not gitignored)
reports/samples/              Committed example evaluation reports (not gitignored)
```

The warehouse data is deliberately deterministic but no longer case-shaped: tickets, ledger events, documents, and snapshot history live in separate JSON datasets with distractor activity. `warehouse_data.seed()` loads those records into `warehouse.db` at the project root, `index.seed_index()` embeds them into `chroma/` with Ollama, and the tools query both. `search_records` is optional semantic retrieval; exact lookups remain the evidence gate. Evaluation labels are stored separately and are never returned by model tools.

## Improvement Changelog

Full per-pass detail lives in `docs/`, linked below. This table is the short version: the story from baseline to final result.

| Stage | What we tried and why | Evidence | Decision |
| --- | --- | --- | --- |
| Baseline (pass 1) | Instruction-only investigator with a runtime evidence gate, 3 fixed cases | Live `INC-001` run: correct diagnosis, cited evidence, 95.7s | Established the starting point; the evidence gate stopped no-data diagnoses |
| Baseline eval (pass 2) | Repeatable 3-case × 3-run baseline, 5-dimension scoring | 9/9 passed (100%), mean 80.5s/run | Kept instruction-only design — no evidence yet that a skill or verifier was needed |
| Expanded challenge (pass 3) | Grew to 12 data-driven cases (partial transfers, duplicates, missing docs, negative controls), 8-dimension safety scoring | 11/12 automated, 12/12 after fixing an evaluator keyword bug | Confirmed the model handled known patterns; scoring bugs can masquerade as model failures |
| Model routing (pass 3a/4) | Compared a naive 3-tier route (4B→8B→27B) against a measured 2-tier route (8B→27B) | Naive: 324s / 65k tokens on `INC-006`; measured: 45s / 8.4k tokens, same correct result | Dropped the 4B tier — it added latency and tokens without improving accuracy |
| Buried evidence (pass 5) | Separated operational data from evaluation labels, removed ticket-title hints, added plausible distractor ledger events and documents | Strict pass rate fell to 5/12 even though raw root-cause accuracy held at 11/12 | Made the baseline honestly harder; exposed unfiltered citations, over-escalation, and one genuine miss |
| Compact context (pass 6) | Rebuilt a filtered evidence bundle per turn instead of resending the full transcript; sent the 27B reviewer only ticket-relevant evidence | Held test coverage; cut prompt growth | Kept — reduced token growth without changing model choice |
| SQLite + retrieval (pass 7) | Replaced JSON fixtures with SQLite-backed adapters; added optional Chroma semantic search | 149 records indexed; existing tool/evaluator contracts unchanged | Kept the adapters; semantic search stayed unused in live traces, so it wasn't the score/latency lever |
| Reliability + finalizer (pass 8) | Fixed a ledger query that dropped evidence when scoped to a ticket; added a deterministic runtime finalizer that pins outcome for 6 evidence shapes the model kept getting wrong | 5/12 (GPU timeouts) → 7/12 → 8/12 → **12/12**, wall clock down to 232s | Kept — the finalizer, not more instruction text, closed the remaining gap |
| Feedback loop (pass 9) | Added a reviewed feedback loop (submit → pending → approve) that exports corrected cases as evaluator-compatible regressions | New regression cases run through the same `evaluate` harness | Kept — corrections become permanent regression tests, not one-off fixes |

**Net result:** on the harder, evidence-buried 12-case suite, strict pass rate went from 5/12 to 12/12, and wall-clock time for the full suite dropped from 706s to 232s — driven by fixing routing/evaluation bugs and adding a deterministic finalizer, not by writing more prompt instructions.

## Hot Take

The biggest, most reliable accuracy gains here did not come from better prompts — they came from taking decisions out of the model's hands wherever the tools already implied the answer. Every attempt to fix a recurring mistake (over-escalating a recoverable stale reservation, missing a transfer leg, mislabeling a pending-post count) by adding another instruction bullet either got ignored or caused a regression on a case that had been passing. What actually closed the gap from 5/12 to 12/12 was a deterministic runtime finalizer that reads the same evidence the model has and pins cause, citations, confidence, and escalation for evidence shapes we could already characterize in code — leaving the model's judgment for the residual ambiguity that's genuinely novel per ticket. Practical lesson: if a failure mode is reliably characterizable from tool output, encode it in the runtime, not the prompt.

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
