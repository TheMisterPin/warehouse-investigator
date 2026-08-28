# Model-routing development note

**Date:** 2026-08-28  
**Status:** automatic 8B/deep-review routing implemented and validated

## Goal

Use the locally installed Ollama models according to their measured behavior, minimizing normal response time while preserving a path to stronger review for uncertain, conflicting, or operationally risky incidents.

Available models:

- `qwen3:4b` — 2.5 GB
- `qwen3:8b` — 5.2 GB
- `qwen3.5:27b` — 17 GB

## Measured model choice

Model size alone did not predict response time on this installation. The installed 4B model continued narrating internal planning even with thinking disabled and exhausted small generation caps, while 8B produced concise tool calls and structured results.

A minimal direct response check produced:

- `qwen3:4b`: exhausted a 64-token cap without completing the requested exact answer
- `qwen3:8b`: returned the exact answer in 3 completion tokens and roughly 0.19 seconds

For that reason, the supported route starts with 8B. The 4B economy tier was removed after the experiment because it added latency and branching without improving the measured result. The generic fixed-model option remains available for deliberate future benchmarks.

## Supported route

```text
qwen3:8b primary investigation
  ├─ clear, high-confidence evidence → return immediately
  └─ uncertainty, conflict, or risk → qwen3.5:27b evidence review
```

The 8B model performs the complete tool investigation. If escalation is needed, 27B receives the gathered ticket, ledger, snapshot, and document evidence in one structured review call. It does not repeat the warehouse tool loop.

## Escalation policy

The primary result escalates to 27B when any of these conditions apply:

- the evidence contains a missing document
- a retry or duplicate inventory effect is detected
- completed transfer records conflict with the current stock snapshot
- the model returns `DUPLICATE_LEDGER_EVENT` or `INSUFFICIENT_EVIDENCE`
- the model requests escalation
- confidence is below 0.80

The router chooses the highest-tier completed result as the final outcome. If a model fails, the next tier is attempted. The response records models used, routing reasons, per-tier time and tokens, outcomes, and trajectory paths.

## Retired economy experiment

```text
qwen3:4b → qwen3:8b → qwen3.5:27b
```

This route was tested as a low-memory option. In practice, 4B frequently produced verbose or incomplete output and could send the same incident through all three tiers. It was therefore slower and more expensive in tokens than beginning with 8B. The profile and its command-line/configuration options have been removed from the supported runtime.

## Live validation

### Clear incident: `INC-001`

The default route used 8B only:

| Metric | Result |
| --- | ---: |
| Final model | `qwen3:8b` |
| Attempts | 1 |
| Time | 7.973 seconds |
| Tokens | 6,873 |
| Outcome | `TRANSFER_NOT_RECEIVED` |
| Confidence | 0.95 |

### Missing-document incident: `INC-006`

The default route used 8B for investigation and 27B for deep review:

| Metric | Result |
| --- | ---: |
| Models | `qwen3:8b` → `qwen3.5:27b` |
| Time | 45.445 seconds |
| Tokens | 8,416 |
| Outcome | `INSUFFICIENT_EVIDENCE` |
| Confidence | 0.60 |
| Escalation | Required |

The 8B pass initially proposed `TRANSFER_NOT_RECEIVED`, but the objective `missing_document` flag forced deep review. The 27B reviewer correctly determined that the missing document prevents a safe diagnosis and preserved escalation.

## Optimization history

The first three-tier implementation repeated the entire tool loop at every model and took 324.199 seconds and 64,977 tokens on `INC-006`. Reusing the evidence bundle reduced that to 95.329 seconds and 21,016 tokens. Making measured-fast 8B the default primary reduced the same path again to 45.445 seconds and 8,416 tokens.

Compared with the naive three-tier version, the final route is about 86% faster and uses about 87% fewer tokens on the representative escalation case.

## Configuration

Use a fixed model for controlled comparisons:

```bash
investigate INC-001 --model qwen3.5:27b
evaluate --model qwen3:8b --case INC-001
```

Override routed models with command options:

```bash
investigate INC-001 \
  --primary-model qwen3:8b \
  --deep-model qwen3.5:27b
```

The same values can be configured with `WAREHOUSE_PRIMARY_MODEL` and `WAREHOUSE_DEEP_MODEL`.

## Verification

- Offline tests cover fast-stop, confidence escalation, high-risk escalation, and evidence-based confidence override.
- A clear case stopped on 8B with the correct outcome.
- A confidently wrong smaller-model diagnosis was overridden by objective missing-document evidence and corrected by 27B.
- Higher tiers reuse evidence and produce their own trajectory files.
