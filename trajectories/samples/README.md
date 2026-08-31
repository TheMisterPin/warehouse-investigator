# Sample trajectories

This directory is exempted from `.gitignore` so a small, representative set of
real agent trajectories can be committed as evidence for the "Agent
trajectories" deliverable.

`trajectories/` (outside this folder) fills up with one JSON file per run and
is gitignored on purpose — it's local working output, not something to
version wholesale.

Before submitting, run a few representative investigations locally and copy
their trajectory files here, for example:

```bash
investigate INC-001                 # clear case, finishes on qwen3:8b
investigate INC-006                 # missing document, escalates to qwen3.5:27b
investigate INC-005                 # duplicate ledger event, escalates and requires review
cp trajectories/INC-001_*.json trajectories/samples/
cp trajectories/INC-006_*.json trajectories/samples/
cp trajectories/INC-005_*.json trajectories/samples/
```

Pick cases that show: a fast single-tier pass, an escalation to the deep
reviewer, and the runtime finalizer overriding or pinning a model decision.
