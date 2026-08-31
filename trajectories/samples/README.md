# Highlighted trajectories

`trajectories/` (one level up) holds every real run from every development
pass — 300+ files. These four are worth opening first if you want the
story without digging through the rest:

- **A clear, single-tier pass** — [`../INC-001_20260828T220304Z.json`](../INC-001_20260828T220304Z.json)
  `qwen3.5:27b` diagnoses a transfer-not-received incident end to end: ticket → ledger →
  snapshot → document → `TRANSFER_NOT_RECEIVED`, confidence 0.95, no escalation. Documented in
  [`docs/01-first-pass-development.md`](../../docs/01-first-pass-development.md).

- **An escalation through all three tiers** — [`../INC-006_route_20260828T231752418576Z.json`](../INC-006_route_20260828T231752418576Z.json)
  A missing transfer document forces escalation past the primary model to `qwen3.5:27b`, which
  correctly returns `INSUFFICIENT_EVIDENCE` and requires escalation rather than guessing.
  Documented in [`docs/03a-model-routing.md`](../../docs/03a-model-routing.md).

- **The retired experiment, actually failing** — [`../qwen3-4b/INC-006_20260828T230753Z.json`](../qwen3-4b/INC-006_20260828T230753Z.json)
  The 4B economy tier alone, on the same `INC-006` ticket: it returns `TRANSFER_NOT_RECEIVED` at
  confidence 0.95 with no escalation — confidently wrong, and unsafe because it doesn't flag the
  missing document. This is the concrete evidence behind removing the 4B tier in
  [`docs/04-fourth-pass-development.md`](../../docs/04-fourth-pass-development.md); the failure mode is
  worse than "slow," it's overconfident on a case that needed escalation.

- **The naive vs. evidence-reuse routing cost** — [`../INC-006_route_20260828T231437363739Z.json`](../INC-006_route_20260828T231437363739Z.json)
  The first 3-tier implementation repeating the full tool loop at every model: 324s and ~65k
  tokens for the same correct answer the 2-tier route later reached in a fraction of the time.

To add more of your own: run `investigate <ticket>` locally and copy the resulting file from
`trajectories/` into this folder, or just link to it from `trajectories/` directly the way the
list above does — nothing here has to be duplicated.
