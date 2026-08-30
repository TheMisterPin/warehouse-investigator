# First-pass development note

**Date:** 2026-08-28  
**Status:** working local prototype

## Purpose

Build the smallest reproducible warehouse-incident investigator that can run entirely through a local Ollama model. The first pass prioritizes a traceable investigation loop over an API, UI, or production data integration.

## What was built

The prototype accepts a ticket ID and runs this loop:

```text
ticket ID
  → Investigator instructions + Ollama
  → read-only warehouse tools
  → structured diagnosis
  → CLI run record + JSON trajectory
```

### Runtime components

| Component | Responsibility |
| --- | --- |
| `instructions/investigator.md` | Investigation procedure, evidence requirements, and cause-code taxonomy |
| `agent.py` | Tool-calling loop, evidence gate, result validation, trace assembly |
| `ollama.py` | Local `/api/chat` client with deterministic settings and tool support |
| `tools.py` | Read-only ticket, ledger, document, and stock-snapshot tools |
| `sample_data.py` | Three deterministic incident fixtures and evaluation ground truth |
| `trajectory.py` | Durable JSON record of model responses, tools, results, and timing |
| `cli.py` | `investigate` command and human-readable JSON response |
| `evaluate.py` | Fixed-case score runner |

## Result contract

Every successful CLI invocation returns:

- the Ollama model name
- wall-clock duration in milliseconds and seconds
- prompt, completion, and total token counts reported by Ollama
- a validated outcome: ticket, root-cause code, summary, cited evidence, recommended action, confidence, and escalation flag
- ordered observable steps: model actions and tool calls with their inputs and outputs
- the path to the complete JSON trajectory

The supported root-cause codes are:

- `TRANSFER_NOT_RECEIVED`
- `STALE_RESERVATION`
- `PENDING_CYCLE_COUNT`
- `INSUFFICIENT_EVIDENCE`

## Evidence gate

The initial implementation allowed the model to emit a technically valid structured response before retrieving data. A first live run reported insufficient evidence without a tool call, which was safe but not useful.

The runner now blocks final structured output until it has collected:

1. the incident ticket
2. the incident ledger events
3. a stock snapshot for the ticket SKU and location
4. every document referenced by the ticket

If the model attempts to diagnose earlier, the runner records the incomplete step and asks it to continue gathering evidence. This makes the baseline traceable and prevents “no-data” diagnoses from passing as investigations.

## Live run: `INC-001`

**Command**

```bash
PYTHONPATH=src python3 -m warehouse_investigator INC-001 --model qwen3.5:27b --max-turns 8
```

**Run telemetry**

| Field | Result |
| --- | --- |
| Model | `qwen3.5:27b` |
| Duration | 95.708 seconds |
| Prompt tokens | 3,305 |
| Completion tokens | 479 |
| Total tokens | 3,784 |
| Root cause | `TRANSFER_NOT_RECEIVED` |
| Confidence | 0.95 |
| Escalation | No |

**Observed investigation path**

1. Retrieved `INC-001` and identified a six-unit shortage at `SEA-01`, related to transfer `TR-100`.
2. Queried the ticket ledger: outbound event `EV-1001` was posted; destination receive event `EV-1002` was pending.
3. Read the `SEA-01` snapshot: 94 physical and available units, with no reservation affecting the number.
4. Retrieved `TR-100`: six units shipped from `PDX-01`, status `in_transit`, no receipt timestamp.
5. Diagnosed a transfer whose destination receipt has not been posted and recommended completing receiving at `SEA-01`.

The complete record is stored at `trajectories/INC-001_20260828T220304Z.json`.

## Validation completed

- Python source and tests compile successfully.
- The offline trace-contract test verifies aggregation of token counts, outcome, ordered steps, and trajectory output without a model runtime.
- A live local run completed through the full tool loop and produced the expected transfer diagnosis.

## Current boundaries

- Warehouse data is an in-memory fixture, not a database or external warehouse-management-system adapter.
- The current evaluator compares only `root_cause_code`; it does not yet score evidence completeness, recommendation quality, confidence calibration, or latency.
- There is no verifier agent, API, authentication, frontend, or persistence layer beyond trajectory files.
- Tool-error retries and model fallback are intentionally not included in this first pass.

## Recommended next pass

1. Run all three fixed cases and capture an evaluation table with accuracy, runtime, and token totals.
2. Add evaluator assertions for cited evidence and escalation behavior, not just cause-code accuracy.
3. Replace the fixture module with a narrow warehouse-data adapter while preserving the existing tool schemas.
4. Add a verifier only if the evaluation exposes recurring factual or reconciliation errors.
