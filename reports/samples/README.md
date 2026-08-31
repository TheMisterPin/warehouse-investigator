# Highlighted reports

`reports/` (one level up) holds every evaluation report from every development pass. These two
are the before/after pair behind the [Improvement Changelog](../../README.md#improvement-changelog):

- **The hard baseline, before the finalizer** — [`../buried-evidence/evaluation_auto-qwen3-8b--qwen3.5-27b_20260828T235524Z.json`](../buried-evidence/evaluation_auto-qwen3-8b--qwen3.5-27b_20260828T235524Z.json)
  `summary.pass_rate: 0.4167` — 5/12 strict passes, 611.5s wall clock, on the 12-case suite once
  ticket-title hints were removed and distractor evidence was added. Root-cause accuracy alone was
  still 11/12; citations, escalation calibration, and one genuine miss (`INC-012`) accounted for the
  gap. Analyzed in [`docs/05-fifth-pass-development.md`](../../docs/05-fifth-pass-development.md).

- **The final result, after the runtime finalizer** — [`../compact-context/evaluation_auto-qwen3-8b--qwen3.5-27b_20260830T223326Z.json`](../compact-context/evaluation_auto-qwen3-8b--qwen3.5-27b_20260830T223326Z.json)
  `summary.pass_rate: 1.0` — 12/12 strict passes, 232.4s wall clock, same suite. Analyzed in
  [`docs/08-eighth-pass-development.md`](../../docs/08-eighth-pass-development.md).

Same 12 cases, same scoring contract, both runs real — that pair is the evidence behind the
changelog's "5/12 → 12/12" claim.

To add a new comparison after further changes: run `evaluate --runs 1` and copy the resulting
report from `reports/` into this folder, or link to it directly the way the list above does.
