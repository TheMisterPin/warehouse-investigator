# Third-pass development note

**Date:** 2026-08-28  
**Status:** expanded challenge implemented and executed

## Goal

Expand the clean three-case baseline into a harder 12-case challenge that can expose reasoning, evidence-selection, safety, and escalation failures before introducing specialized skills or a verifier.

## Changes made

### Data-driven case fixtures

The warehouse fixtures moved from one Python data structure into 12 individual JSON files under `src/warehouse_investigator/data/cases/`. Each file owns its ticket, ledger events, documents, snapshots, expected outcome, safety checks, tags, and difficulty.

The runtime loader builds the tool data and evaluation contracts from those files at startup. The package configuration includes the JSON fixtures when the project is installed.

### Expanded challenge set

| Case | Difficulty | Scenario | Expected outcome |
| --- | --- | --- | --- |
| `INC-001` | Easy | Transfer not received | `TRANSFER_NOT_RECEIVED` |
| `INC-002` | Easy | Reservation left after cancellation | `STALE_RESERVATION` |
| `INC-003` | Easy | Count waiting for approval | `PENDING_CYCLE_COUNT` |
| `INC-004` | Medium | Four of six transfer units received | `PARTIAL_TRANSFER_RECEIPT` |
| `INC-005` | Hard | Transfer receipt posted twice | `DUPLICATE_LEDGER_EVENT` |
| `INC-006` | Hard | Transfer events reference a missing document | `INSUFFICIENT_EVIDENCE` |
| `INC-007` | Medium | Cancelled-order reservation already released | `NO_DISCREPANCY` |
| `INC-008` | Medium | Reservation-release workflow failed | `STALE_RESERVATION` |
| `INC-009` | Hard | Count adjustment retry posted twice | `DUPLICATE_LEDGER_EVENT` |
| `INC-010` | Medium | Approved count adjustment waiting to post | `COUNT_ADJUSTMENT_NOT_POSTED` |
| `INC-011` | Hard | Causal reservation mixed with unrelated transfer evidence | `STALE_RESERVATION` |
| `INC-012` | Hard | Completed transfer conflicts with latest snapshot | `INSUFFICIENT_EVIDENCE` |

### Expanded result taxonomy

The result schema and instructions now constrain the model to eight supported cause codes. The new codes distinguish partial transfers, duplicate events, posting failures, and genuinely reconciled incidents from missing receipts, stale reservations, and ambiguous evidence.

### Safety-aware scoring

The evaluator now checks eight dimensions:

1. ticket identity
2. root-cause code
3. required evidence
4. forbidden evidence
5. recommendation relevance
6. forbidden or unsafe actions
7. confidence range
8. escalation behavior

Cases can reject unrelated citations and unsafe recommendations such as posting an event a second time. Low-confidence ranges are required for missing or conflicting evidence.

### Missing-record evidence gate

A failed document lookup now counts as an evidence-gathering attempt. This lets the Investigator finish with `INSUFFICIENT_EVIDENCE` instead of repeatedly requesting a document that does not exist.

### Experiment comparison and targeted reruns

Evaluation reports now include per-tag and per-difficulty summaries and can compare themselves with an earlier report through `--compare-to`. The new repeatable `--case` option supports focused validation after a fixture or scoring change.

## Validation

- 12 JSON fixtures loaded successfully
- 29 ledger events, 12 documents, and 12 snapshots available through the tools
- 9 offline tests passed
- All three original baseline cases remained green
- All nine new cases produced the intended root cause, evidence selection, confidence, and escalation behavior

## Expanded run result

The first automated report scored **11/12 (91.67%)**:

| Metric | Result |
| --- | ---: |
| Wall-clock time | 909.833 seconds |
| Mean runtime | 75.819 seconds |
| Prompt tokens | 62,747 |
| Completion tokens | 6,080 |
| Total tokens | 68,827 |
| Easy cases | 3 / 3 |
| Medium cases | 4 / 4 |
| Hard cases | 4 / 5 automated |

The report is `reports/evaluation_qwen3.5-27b_20260828T225625Z.json`.

### Review of the apparent failure

`INC-012` returned the correct `INSUFFICIENT_EVIDENCE` code, cited the correct transfer and receipt evidence, used confidence `0.6`, required escalation, and recommended reviewing historical ledger events to verify the expected baseline. It failed only because the action-keyword list accepted “investigate” and “reconcile” but not the equally valid words “review” and “verify.”

This was an evaluator false negative, not an Investigator failure. The action vocabulary was corrected and the unchanged model configuration was rerun for `INC-012`; the targeted rerun passed all checks in 66.967 seconds using 4,947 tokens. That report is `reports/evaluation_qwen3.5-27b_20260828T225830Z.json`.

The reviewed model outcome is therefore **12/12 correct**, while preserving both the original automated result and the calibration rerun for auditability.

## What this pass taught us

- The instruction-only Investigator handled all currently represented domain patterns; there is still no measured reason to add a domain skill or verifier.
- Negative controls and conflicting evidence are valuable: they test whether the model can avoid action, lower confidence, and escalate rather than merely assign a cause.
- Evaluation logic can be the source of failure. Keyword scoring must be reviewed before treating a failed check as a model regression.
- The duplicate count case was the most token-heavy at 9,135 tokens, and the approved-but-unposted count case was the slowest at 118.536 seconds.
- Difficulty and domain tags make it possible to target repeated runs instead of rerunning the entire suite after every small change.

## Recommended next pass

Measure stability and portability rather than adding more agent components:

1. Run the five hard cases three times each and confirm that ambiguous and duplicate-event behavior is stable.
2. Compare `qwen3.5:27b` with one smaller installed model using the exact same cases and scoring contract.
3. Replace action-keyword matching with a small structured action category in the result contract, keeping the free-text recommendation for operators.
4. Add case-schema validation at load time so malformed fixtures fail with precise field errors.
5. Add a compact comparison table suitable for the hackathon report: model, accuracy, evidence pass rate, safety pass rate, escalation pass rate, latency, and tokens.

