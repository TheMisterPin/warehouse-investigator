# Second-pass development note

**Date:** 2026-08-28  
**Status:** baseline evaluation harness complete

## Goal

Turn the initial three-case evaluator into a repeatable baseline that measures more than whether the model selected the right root-cause label.

The main question for this pass was: does the instruction-only Investigator repeatedly produce a diagnosis that is correct, evidenced, actionable, and safe to use without adding a domain skill or verifier?

## Changes made

### Richer case contracts

Each evaluation case now defines:

- the expected root-cause code
- evidence IDs that must appear in the conclusion
- acceptable action terms for the recommendation
- the expected escalation decision

These expectations live beside the deterministic warehouse fixtures so the evaluator and source data stay synchronized.

### Multi-part outcome scoring

The evaluator now checks five dimensions independently:

1. ticket identity
2. root-cause accuracy
3. required evidence coverage
4. recommendation relevance
5. escalation behavior

A run passes only when all five checks pass. Failed reports identify the exact dimensions that missed and retain the model outcome for diagnosis.

### Repeated baseline runs

The evaluation command now supports `--runs`, with three repetitions per case as the default. It continues after an individual run error so one failure does not erase the rest of an experiment.

### Durable experiment reports

Each evaluation writes a timestamped JSON report containing:

- model and evaluation configuration
- per-run pass/fail checks
- model outcome and trajectory path
- elapsed time and token usage per run
- overall and per-case pass rates
- aggregate wall-clock time and token totals

Individual model/tool trajectories remain separate, keeping the summary report compact while preserving a complete audit trail.

### Test coverage and setup

Offline tests now cover successful scoring, missing-evidence rejection, trace/token aggregation, result validation, and warehouse tool fixtures. A project-local virtual environment was created and the full suite passes.

## Validation result

The complete baseline used `qwen3.5:27b`, temperature 0, a maximum of eight turns, three cases, and three repetitions per case.

| Result | Value |
| --- | ---: |
| Passed runs | 9 / 9 |
| Pass rate | 100% |
| Mean runtime | 80.460 seconds |
| Runtime range | 51.874–125.660 seconds |
| Total tokens | 36,240 |
| Mean tokens per run | 4,026.7 |
| Offline tests | 5 passed |

The detailed analysis is in `docs/02-baseline-evaluation.md`; the machine-readable report is `reports/baseline_qwen3.5-27b_20260828T222732Z.json`.

## Decisions from this pass

- Keep the instruction-only Investigator as the baseline. The measured cases do not expose a recurring reasoning failure that warrants a skill.
- Do not add a verifier yet. It would add latency and complexity without a demonstrated accuracy benefit on the current set.
- Treat evidence and action quality as first-class evaluation outputs, not optional commentary around the cause code.
- Track latency separately from token usage. Identical deterministic outputs still showed substantial runtime variation on local hardware.
- Expand challenge coverage before connecting production data or adding application layers.

## Known limitations

- Three clean, single-cause cases are not a representative reliability test.
- Keyword-based recommendation checks are useful guardrails, not semantic safety evaluation.
- There are no checks yet for irrelevant citations, dangerous actions, unsupported certainty, or unnecessary escalation.
- The fixture format is Python code, which will become awkward as the case set grows.
- Only one model and one local hardware configuration have been measured.

## Exit criteria achieved

- Repeatable evaluation command implemented
- Structured per-case expectations implemented
- Evidence and action checks implemented
- Aggregate latency and token reporting implemented
- Full baseline executed and preserved
- Offline tests passing

