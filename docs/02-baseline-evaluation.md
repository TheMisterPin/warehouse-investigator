# Baseline evaluation

**Date:** 2026-08-28  
**Model:** `qwen3.5:27b`  
**Configuration:** 3 incident cases × 3 repetitions, temperature 0, maximum 8 turns

## Objective

Measure whether the instruction-only Investigator consistently reaches the correct warehouse diagnosis using relevant evidence and a useful next action. This phase also establishes latency and token baselines before adding domain skills, a verifier, or production data adapters.

## Passing criteria

A run passes only when all five checks succeed:

1. The returned ticket ID matches the requested incident.
2. The root-cause code exactly matches the case definition.
3. The result cites every required event and document ID.
4. The recommended action is substantive and contains a case-relevant action term.
5. The escalation decision matches the case expectation.

This is intentionally stricter than the first evaluator, which checked only the root-cause code.

## Results

| Metric | Result |
| --- | ---: |
| Passed runs | 9 / 9 |
| Overall pass rate | 100% |
| `INC-001` transfer receipt | 3 / 3 |
| `INC-002` stale reservation | 3 / 3 |
| `INC-003` pending cycle count | 3 / 3 |
| Wall-clock time | 724.151 seconds |
| Mean time per run | 80.460 seconds |
| Fastest run | 51.874 seconds |
| Slowest run | 125.660 seconds |
| Prompt tokens | 31,731 |
| Completion tokens | 4,509 |
| Total tokens | 36,240 |
| Mean tokens per run | 4,026.7 |

The machine-readable result is stored at `reports/baseline_qwen3.5-27b_20260828T222732Z.json`. Each record links to its complete trajectory under `trajectories/evaluation/`.

## Case outcomes

### `INC-001` — transfer not received

All three runs returned `TRANSFER_NOT_RECEIVED`, cited transfer `TR-100` and pending receipt event `EV-1002`, and recommended posting the receipt at `SEA-01`.

### `INC-002` — stale reservation

All three runs returned `STALE_RESERVATION`, cited order `SO-900` plus reservation/cancellation events `EV-2001` and `EV-2002`, and recommended releasing the nine-unit reservation.

### `INC-003` — pending cycle count

All three runs returned `PENDING_CYCLE_COUNT`, cited count `CC-300` and event `EV-3001`, and recommended approving the count so the adjustment can post.

## Observations

- At temperature 0, each case produced identical token counts and materially identical outcomes across repetitions.
- Runtime still varied substantially even when token counts were identical. Local inference latency ranged from roughly 52 to 126 seconds, so runtime should be reported separately from output quality.
- The evidence gate prevented premature no-data diagnoses in every measured run.
- No recurring domain-reasoning failure appeared in this fixture set, so the current evidence does not justify adding a specialized skill or verifier yet.

## Limits of this baseline

- Three cases are enough to verify the harness, but not enough to establish broad reliability.
- The cases are clean, single-cause fixtures with complete evidence. They do not test conflicting events, partial receipts, retries, missing records, or multiple plausible causes.
- Recommendation scoring uses case-relevant keywords. It catches empty or irrelevant actions but does not deeply judge operational safety.
- The runs use deterministic local fixtures and one model on one machine; they do not measure model or hardware portability.

## Recommended next phase

Expand the evaluation set before adding architecture:

1. Grow from 3 to 12 cases, including partial transfers, duplicate events, missing documents, already-released reservations, count retries, normal/no-incident cases, and ambiguous evidence that should escalate.
2. Add negative evidence checks so a diagnosis fails when it cites an unrelated event or recommends an unsafe stock adjustment.
3. Run the expanded set once to identify actual recurring failures.
4. Add a narrow domain playbook or independent verifier only for a measured failure pattern, then rerun the same cases to quantify the improvement.

