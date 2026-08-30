# Eighth development pass: reliability, calibration, and a runtime finalizer

**Date:** 2026-08-30  
**Status:** implemented, evaluated at 12/12, and retained as the current routed baseline

## Objective

Make the 12-case auto-route eval finish without GPU timeouts, then stop losing the same cases to sampling. Procedure text was already correct; 8B and 27B still ignored it. This pass moved those rules into runtime so a case that passes once does not fail the next run, and so 27B is not asked to re-decide evidence the tools already imply.

Seventh-pass Chroma search was left unused. Live traces never called `search_records`. Score and latency moved with workers, timeouts, ledger query shape, and a post-model finalizer — not with semantic retrieval.

## Why

A four-worker compact-context run scored 5/12 in 706s because four 27B reviews hit the 180s HTTP timeout while sharing one Ollama instance. Root cause was often right; strict scoring failed on escalation, citations, and a few wrong codes. Replicating at `--workers 2` with a 300s 27B timeout and one retry produced 7/12 in ~768s with zero timeouts. Tokens stayed ~60k (mostly prompt). The remaining misses were stable: stale-reservation over-escalation, a missing transfer shipment citation, and a pending-post count classified as pending approval.

More instruction bullets did not hold. After ticket-scoped ledger queries, 27B could see both transfer legs on `INC-006` and still call it `TRANSFER_NOT_RECEIVED`. On `INC-012`, 27B spent ~45s and called conflicting stock `NO_DISCREPANCY`. Extra 27B was costing time and creating regressions.

## Reliability

- Default `--workers` became 2, then 1 after serial runs proved faster on this machine (no GPU contention). `--workers 2` remains available.
- Primary (8B) HTTP timeout stays 180s; deep review (27B) is 300s.
- A timed-out 27B review retries once, then falls back to the 8B result.
- `--compare-to` records worker counts, wall clock, and mean case time so two reports can be compared without a spreadsheet.

## Calibration

Investigator procedure was tightened for recoverable stale reservations (`requires_escalation: false`), citing both transfer legs when a document is missing, and distinguishing `PENDING_CYCLE_COUNT` from `COUNT_ADJUSTMENT_NOT_POSTED`.

Routing grew two evidence flags that later became finalizer inputs:

- `pending_post` — approved count whose adjustment is still waiting to post
- `posted_release` — posted `reservation_released` with reserved quantity 0
- `partial_transfer` (already detected) — document status `partially_received`

A 1-worker calibration eval reached 8/12 in 391s. Escalation cases `INC-002`, `INC-008`, and `INC-011` passed on 8B. `INC-010` reached 27B and passed. `INC-003`, `INC-004`, and `INC-007` regressed because 8B skipped 27B after the tighter escalation rule.

## Ticket-scoped ledger

`query_ledger` ANDed `location` even when `ticket_id` was set. 8B often passed `location=SEA-01`, which dropped the PDX shipment `EV-6001` on `INC-006`. 27B then honestly reported that no outbound event existed.

When `ticket_id` is present, `sku` and `location` are ignored and the full ticket ledger is returned. That matches the tool docstring: ticket results can include unrelated activity that must be reconciled. Location and SKU filters still apply when there is no ticket id.

The following 1-worker eval stayed 8/12. Lookup worked: `INC-006` cited both legs, then 27B over-diagnosed `TRANSFER_NOT_RECEIVED`. `INC-007` passed via 27B. `INC-012` failed because 27B closed the ticket. Wall clock rose to 452s because more cases went to 27B.

## Runtime finalizer

After the model returns JSON, `finalize_outcome` applies the procedure to retrieved evidence. The model still writes the summary. Cause, citations, confidence cap, escalation, and a small set of actions are constrained when the tools already decide them.

| Evidence already in hand | Runtime result | Skips 27B |
| --- | --- | --- |
| Citation outside ticket window, ticket documents, or ticket SKU | Dropped (same rule as the 27B review filter) | — |
| `get_document` error | `INSUFFICIENT_EVIDENCE`, escalate, confidence ≤ 0.7 | yes |
| Completed transfer vs ticket expected (`conflicting_stock`) | `INSUFFICIENT_EVIDENCE`, escalate, confidence ≤ 0.7 | yes |
| Posted `reservation_released` and reserved stock 0 | `NO_DISCREPANCY` | yes |
| Document `partially_received` | `PARTIAL_TRANSFER_RECEIPT`; add the pending remainder event id | yes |
| Ledger `pending_post` | `COUNT_ADJUSTMENT_NOT_POSTED` | yes |
| Duplicate posted effect | Unchanged; still sent to 27B | no |

Duplicate detection wins over `conflicting_stock` so `INC-005` is not rewritten as insufficient evidence. The finalizer is procedure-level: it does not branch on ticket ids or read `ground_truth.json`.

Routing then escalates only for remaining risk: `duplicate_event`, low confidence, explicit escalation, or unpinned `INSUFFICIENT_EVIDENCE` / `DUPLICATE_LEDGER_EVENT`. Pinned outcomes stop at 8B.

## Live evaluation

All runs below used `evaluate --runs 1` with auto routing `qwen3:8b` → `qwen3.5:27b` and compact-context trajectory/report dirs, except the first timeout run (workers=4).

| Report | Workers | Strict | Wall (s) | Mean case (s) | Tokens | 27B |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Timeout (4-wide, 180s 27B limit) | 4 | 5/12 | 706 | 192 | 59,168 | 4 timed out |
| `...T213107Z.json` | 2 | 7/12 | 768 | 124 | 65,808 | 0 timeouts |
| `...T215635Z.json` | 1 | 8/12 | 391 | 33 | 65,909 | fewer reviews |
| `...T221932Z.json` | 1 | 8/12 | 452 | 38 | 70,539 | 7 reviews |
| `...T223326Z.json` | 1 | **12/12** | **232** | **19** | 60,952 | 2 reviews |

Final command:

```bash
evaluate --runs 1 \
  --trajectory-dir trajectories/compact-context \
  --report-dir reports/compact-context \
  --compare-to reports/compact-context/evaluation_auto-qwen3-8b--qwen3.5-27b_20260830T221932Z.json
```

Report: `reports/compact-context/evaluation_auto-qwen3-8b--qwen3.5-27b_20260830T223326Z.json`

On this run only `INC-005` and `INC-009` reached 27B (duplicate ledger events). The other ten cases finished on 8B in 10–16s. `search_records` was still unused.

## Offline verification

62 tests pass without Ollama, including ticket-scoped ledger queries, finalizer pins for the six evidence shapes above, citation filtering of historical `EV-H*` ids, skip-27B routing when a cause is pinned, and compare-report time/worker deltas.

## What this pass is not

The investigator is no longer the last word on cause, citations, or escalation when retrieved evidence already implies them. That is the point: those fields were the unstable part of strict scoring. Summary text remains generated. A genuinely ambiguous ticket with no pinning flags still goes to 27B.

Semantic search remains available and unused. It is not the current score or latency lever.
