# Seventh development pass: SQLite warehouse and Chroma retrieval

**Date:** 2026-08-30  
**Status:** implemented and covered by offline tests

## Objective

Replace the in-memory JSON loaders with a file-backed warehouse, then add semantic search so the investigator can find related records by meaning without dropping the exact lookup tools the evidence gate and evaluator depend on.

The fifth pass already separated operational JSON from evaluation labels and told later work to swap `warehouse_data.py` for database adapters. This pass does that swap, then layers a vector index on the same records.

## Why

JSON lists were enough to prove the tool loop, but they are not how a warehouse system is queried. Putting tickets, ledger events, documents, and snapshots in SQLite makes the adapters look like the interface a real WMS would expose: lookup by ID, filter ledger by ticket/SKU/location, return snapshot history newest first.

Buried evidence is still the hard part of the 12-case suite. Exact tools require the model to already know an ID, SKU, or location. Semantic search lets it ask for “in-transit transfer to SEA-01” and get candidate documents and events, then confirm them with `get_document` / `query_ledger`. Evaluation labels stay out of both stores so a search hit cannot leak the answer.

## SQLite warehouse

Operational JSON remains the source of truth. `warehouse_data.seed()` rebuilds `warehouse.db` at the project root (gitignored) from `data/warehouse/*.json`.

| Table | Shape |
| --- | --- |
| `tickets` | typed columns; `document_refs` stored as JSON |
| `ledger_events` | typed columns; indexed on ticket, SKU, location |
| `documents` | `id`, `type`, `sku`, plus a JSON `payload` so transfer / cycle-count / sales-order fields round-trip |
| `snapshots` | typed columns keyed by `snapshot_id` |

Tools now query these tables and return the same dict shapes as before. If the database file is missing, the first lookup seeds it. Evaluation `ground_truth.json` is never written to SQLite. Tests point at a temp database so they do not touch the root file.

## Chroma index

`index.seed_index()` embeds every ticket, ledger event, document, and snapshot into one collection in project-root `chroma/` (gitignored). Vectors come from Ollama (`nomic-embed-text` via `/api/embed`), not from Chroma’s built-in embedder. Each item stores `record_type` and `record_id` metadata; search hydrates the full record from SQLite.

`python -m warehouse_investigator.seed` rebuilds both stores. `search_records` also indexes on first use if the collection is empty.

The new tool is additive:

```text
search_records(query, record_type?, n?)
```

`record_type` may be `ticket`, `ledger_event`, `document`, or `snapshot`. Hits include the hydrated record and cosine distance. The evidence gate is unchanged: diagnosis still requires `get_ticket`, `query_ledger`, `get_snapshot`, and ticket documents. Search results are appended to the compact evidence bundle so the next turn can see them. Deep review keeps only hits that match the ticket SKU, location, or document refs.

Investigator instructions tell the model it may search after `get_ticket` and must confirm anything it cites with the exact lookup tools.

## Offline verification

Tests inject a hash embedder and a temp Chroma path, so the suite does not need Ollama. Seed, hydration, `record_type` filters, evidence-bundle search results, and the existing tool/evaluator contracts all pass without a model runtime. A live seed against local Ollama indexed 149 records (12 / 65 / 36 / 36).
