# Fifth development pass: separated data and buried evidence

**Date:** 2026-08-28  
**Status:** implemented, evaluated, and retained as the new harder baseline

## Objective

Replace case-shaped fixtures with operational datasets that resemble separate warehouse systems, remove diagnosis hints from tickets, and test whether the investigator can find relevant evidence among plausible noise.

The previous fixtures stored a ticket, its ledger events, documents, snapshots, and expected answer together in one file. The model could not directly read the expected answer, but the structure was optimized around each evaluation case and several ticket titles or notes described the root cause too clearly.

## Data architecture

Model-visible records now live in separate files:

```text
data/warehouse/tickets.json
data/warehouse/ledger_events.json
data/warehouse/documents.json
data/warehouse/snapshots.json
```

Evaluator-only labels live separately:

```text
data/evaluation/ground_truth.json
```

`warehouse_data.py` loads only operational records for tools. `evaluation_data.py` loads scoring labels for the evaluator. Model tools never import or return the evaluation labels.

## How the evidence was buried

Each incident now includes three distractor ledger events in addition to its relevant evidence:

- a completed historical cycle count for the same SKU and location, outside the ticket's investigation window
- the posted adjustment for that historical count
- recent transfer activity for a different SKU at the same location

The corresponding historical and unrelated documents exist in the document dataset, so they are plausible records rather than obvious broken references. Every distractor ID is included in the hidden `forbidden_evidence_ids` list.

Tickets were rewritten as neutral reconciliation alerts. They retain the reported quantities, SKU, location, document references, and time window, but their title and notes no longer state clues such as “posted twice,” “missing document,” or “four of six received.”

Snapshots are stored as history rather than one record per case. `get_snapshot` returns the newest record at the top level and older matching records under `history`, with `captured_at` timestamps for reconciliation.

Ledger results are sorted newest first. The investigator instructions now explicitly require correlation by SKU, location, document ID, state, and timestamp instead of treating every event attached to a ticket as evidence.

## Supporting implementation changes

- replaced the combined `sample_data.py` loader with separate operational and evaluation loaders
- removed the 12 combined case JSON files
- updated package data rules for the new directory layout
- updated tools to query the separated datasets
- added data-integrity, distractor, and snapshot-history tests
- tightened the router's conflicting-stock flag so unrelated completed transfers cannot trigger deep review

## Offline verification

All 15 offline tests passed.

## Routed evaluation result

Command:

```bash
evaluate --runs 1 \
  --trajectory-dir trajectories/buried-evidence \
  --report-dir reports/buried-evidence
```

Report:

```text
reports/buried-evidence/evaluation_auto-qwen3-8b--qwen3.5-27b_20260828T235524Z.json
```

### Aggregate result

| Metric | Result |
| --- | ---: |
| Strict passes | 5/12 (41.7%) |
| Correct root cause | 11/12 (91.7%) |
| Safe recommended action | 12/12 (100%) |
| Required evidence check | 11/12 (91.7%) |
| Forbidden evidence check | 9/12 (75.0%) |
| Escalation calibration | 8/12 (66.7%) |
| Confidence calibration | 11/12 (91.7%) |
| Total time | 611.548 seconds |
| Mean time per case | 50.962 seconds |
| Total tokens | 128,217 |
| Mean tokens per case | 10,684.8 |

Four cases finished on `qwen3:8b`; eight reached `qwen3.5:27b` review.

### Strict passes

- `INC-003` — pending cycle count
- `INC-005` — duplicate transfer receipt
- `INC-007` — no discrepancy negative control
- `INC-009` — duplicate count adjustment
- `INC-010` — count adjustment not posted

All three cycle-count cases passed. Both duplicate-event cases passed, including the requirement to recommend controlled review/reversal and require escalation.

### Failures that still had the correct diagnosis

| Case | Correct diagnosis | Strict failure |
| --- | --- | --- |
| `INC-001` | `TRANSFER_NOT_RECEIVED` | cited unrelated `EV-X001` |
| `INC-002` | `STALE_RESERVATION` | unnecessary escalation |
| `INC-004` | `PARTIAL_TRANSFER_RECEIPT` | cited historical `EV-H004A` and `EV-H004B` |
| `INC-006` | `INSUFFICIENT_EVIDENCE` | omitted required `EV-6001` |
| `INC-008` | `STALE_RESERVATION` | unnecessary escalation |
| `INC-011` | `STALE_RESERVATION` | unnecessary escalation |

### Genuine diagnostic miss

`INC-012` was the only wrong root cause. Both tiers returned `NO_DISCREPANCY` even though the completed transfer records conflict with the latest quantity. The final answer also cited the old historical count events, used high confidence, recommended closing the ticket, and declined escalation. This is the highest-priority safety failure for the next pass.

## Interpretation

The model remains strong at recognizing root-cause patterns after ticket hints are removed: 11 of 12 diagnoses were correct. The stricter 5-of-12 result shows that diagnosis alone is not enough for an auditable operational agent.

The new baseline exposes three concrete weaknesses:

1. Evidence citations are generated from the full observed context instead of a final relevance-filtered set.
2. Recoverable reservation failures are often treated as requiring human escalation even when the recommended action is straightforward.
3. The deep reviewer can preserve an unsafe conclusion despite an objective conflicting-stock routing flag, as shown by `INC-012`.

## Recommended next pass

Add a deterministic post-investigation evidence filter and policy verifier before accepting the final result:

- reject evidence IDs outside the ticket SKU, relevant documents, location, and investigation window
- require the model to cite every decisive ledger leg for ambiguity outcomes
- derive or validate escalation from the root-cause policy rather than trusting the model alone
- reject `NO_DISCREPANCY` when objective conflict flags are present
- rerun only the seven failed cases first, then run the full suite after targeted checks pass

This should improve auditability without spending more model tokens or adding another model tier.

