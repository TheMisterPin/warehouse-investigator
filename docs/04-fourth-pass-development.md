# Fourth development pass: simplify model routing

**Date:** 2026-08-28  
**Status:** implemented and verified

## Objective

Reduce latency and configuration complexity by turning the model-routing experiment into one supported production path:

```text
qwen3:8b primary investigation
  ├─ clear and safe → return result
  └─ ambiguous or high-risk → qwen3.5:27b evidence review
```

## Why multiple models were tried

The initial routing design tested all three locally available Ollama models:

- `qwen3:4b` as a small, potentially inexpensive first pass
- `qwen3:8b` as a balanced tool-using investigator
- `qwen3.5:27b` as the strongest reviewer for difficult cases

The hypothesis was that most incidents could finish on the smallest model, reserving larger models for uncertainty. This was worth measuring because model size, memory use, latency, tool reliability, and answer quality do not necessarily move together on local hardware.

The experiment first used a three-tier economy route. It also tested evidence reuse so that an escalated model could review already gathered warehouse facts instead of repeating every tool call.

## What the measurements showed

The 4B model did not behave like a useful fast tier on this installation. In a minimal direct-response check, it exhausted a 64-token output cap without completing the requested exact answer. The 8B model returned the exact answer in three completion tokens in roughly 0.19 seconds.

The routing measurements reinforced that result:

| Route and case | Time | Tokens | Result |
| --- | ---: | ---: | --- |
| 8B only on clear `INC-001` | 7.973 s | 6,873 | Correct |
| 8B → 27B on ambiguous `INC-006` | 45.445 s | 8,416 | Correct |
| Naive 4B → 8B → 27B on `INC-006` | 324.199 s | 64,977 | Correct, but inefficient |
| Evidence-reuse 4B → 8B → 27B on `INC-006` | 95.329 s | 21,016 | Correct, but still slower |

These are representative warm-model runs, not universal hardware guarantees. Cold model loading can add latency.

## Decision

Use `qwen3:8b` as the only supported primary investigator and `qwen3.5:27b` as the selective deep reviewer.

The 4B economy tier was removed because it:

- did not provide the expected response-time advantage
- was less concise and reliable for structured tool use
- introduced an extra routing branch and configuration surface
- could increase total latency and token usage before reaching the same reviewer

The generic `--model <name>` option remains. It is intentionally a fixed-model experiment/debugging interface, not a supported 4B route. This keeps the runtime open to future model comparisons without carrying a weak automatic path.

## Changes in this pass

- removed the `economy` routing profile
- removed the `--routing-profile` and `--small-model` command options
- removed `WAREHOUSE_SMALL_MODEL`
- removed the three-tier routing constants and escalation rules
- changed the base Ollama client fallback from `qwen3:4b` to `qwen3:8b`
- kept `--primary-model`, `--deep-model`, and fixed `--model` overrides
- simplified routing tests to cover the supported two-tier behavior
- updated the README and model-routing documentation

## Supported behavior after this pass

Clear, high-confidence incidents finish on 8B. The result moves to 27B when objective evidence indicates a missing document, duplicate inventory effect, or conflicting stock; when the primary returns a high-review outcome; when it explicitly requests escalation; or when confidence is below 0.80.

The 27B reviewer receives the evidence already gathered by 8B in one structured call. Responses and trajectories continue to report the final model, total time, prompt/completion tokens, outcome, routing reasons, and observable investigation steps.

## Future reconsideration criteria

A smaller primary tier should be reconsidered only if a new model demonstrates all of the following on the fixed evaluation suite:

- lower end-to-end latency than 8B
- reliable tool calls and structured output
- comparable case accuracy and safe actions
- fewer total tokens after escalation, not merely lower memory use

Until then, the two-tier route is the smallest system supported by the measurements.
