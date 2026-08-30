# Sixth development pass: compact context and concurrent evaluation

**Date:** 2026-08-30  
**Status:** implemented and covered by offline tests

## Objective

Reduce prompt growth and wasted tool turns during a single investigation, send the 27B reviewer only ticket-relevant evidence, and run the 12-case evaluation as four concurrent investigations at a time.

## Context compaction

The primary investigator no longer resends the full chat transcript on every turn. Before each model call it rebuilds a short view:

- system procedure
- the original ticket request
- one evidence bundle with unique retrieved records and a single gate status

Model-facing snapshots omit historical rows whose quantities match the latest record. Ledger results still include buried distractors so the 8B model has to correlate. Unfiltered ledger queries now return an error instead of the entire dataset. Trajectories continue to store full tool results.

After the evidence gate is complete, tools are disabled and the JSON result schema is required. Duplicate tool calls return `already_fetched` instead of refetching. The long evidence-gate checklist was removed from the investigator instructions; runtime blocks diagnosis until the ticket, ledger, snapshot, and ticket documents are present.

## Deep-review payload

When 8B escalates, 27B receives a filtered bundle: the ticket, ticket documents (including missing-document errors), latest ticket snapshot, and ledger events whose SKU matches the ticket and that either cite a ticket document or fall inside the investigation window. Other-SKU noise, historical count legs, extra documents, and unchanged snapshot history are omitted. Routing flags are still computed from the full 8B tool trace.

## Concurrent evaluation

`evaluate` now runs up to four ticket investigations at once (`--workers 4` by default). The twelve-case suite therefore completes in three waves instead of twelve sequential runs. Report configuration records the worker count. Use `--workers 1` for a serial baseline.

## Offline verification

Context, agent-loop, routing-filter, and concurrent-evaluation tests pass without Ollama.
