"""Chroma index of warehouse records, embedded with Ollama."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .embeddings import Embedder, OllamaEmbedder
from .warehouse_data import (
    get_document,
    get_ledger_event,
    get_snapshot_record,
    get_ticket,
    list_documents,
    list_ledger_events,
    list_snapshots,
    list_tickets,
    project_root,
)

COLLECTION_NAME = "warehouse"
RECORD_TYPES = ("ticket", "ledger_event", "document", "snapshot")
DEFAULT_SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 20
_EMBED_BATCH = 32

_override_chroma_path: Path | None = None
_override_embedder: Embedder | None = None


def default_chroma_path() -> Path:
    return project_root() / "chroma"


def resolve_chroma_path(chroma_path: Path | None = None) -> Path:
    if chroma_path is not None:
        return Path(chroma_path)
    if _override_chroma_path is not None:
        return _override_chroma_path
    return default_chroma_path()


def get_embedder() -> Embedder:
    if _override_embedder is not None:
        return _override_embedder
    return OllamaEmbedder()


def _chroma_client(chroma_path: Path | None = None):
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    import chromadb

    path = resolve_chroma_path(chroma_path)
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def _metadata_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _embed_text(record_type: str, record: dict[str, Any]) -> str:
    if record_type == "ticket":
        refs = " ".join(record.get("document_refs") or [])
        return (
            f"ticket {record['id']}. {record.get('title', '')}. "
            f"SKU {record.get('sku')} location {record.get('location')}. "
            f"expected {record.get('expected_quantity')} observed {record.get('observed_quantity')}. "
            f"documents {refs}. notes {record.get('notes', '')}."
        )
    if record_type == "ledger_event":
        return (
            f"ledger event {record['id']} ticket {record.get('ticket_id')}. "
            f"SKU {record.get('sku')} location {record.get('location')}. "
            f"{record.get('event_type')} quantity_delta {record.get('quantity_delta')} "
            f"document {record.get('document_id')} state {record.get('state')} "
            f"at {record.get('timestamp')}."
        )
    if record_type == "snapshot":
        return (
            f"snapshot {record.get('snapshot_id')} SKU {record.get('sku')} location {record.get('location')}. "
            f"physical {record.get('physical_quantity')} reserved {record.get('reserved_quantity')} "
            f"available {record.get('available_quantity')} captured_at {record.get('captured_at')}."
        )
    parts = [f"document {record.get('id')} type {record.get('type')}"]
    for key, value in record.items():
        if key in {"id", "type"} or value is None:
            continue
        parts.append(f"{key} {value}")
    return ". ".join(parts)


def _index_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for ticket in list_tickets().values():
        items.append(
            {
                "id": f"ticket:{ticket['id']}",
                "record_type": "ticket",
                "record_id": ticket["id"],
                "sku": ticket.get("sku"),
                "location": ticket.get("location"),
                "ticket_id": ticket["id"],
                "document": _embed_text("ticket", ticket),
            }
        )
    for event in list_ledger_events():
        items.append(
            {
                "id": f"ledger_event:{event['id']}",
                "record_type": "ledger_event",
                "record_id": event["id"],
                "sku": event.get("sku"),
                "location": event.get("location"),
                "ticket_id": event.get("ticket_id"),
                "document": _embed_text("ledger_event", event),
            }
        )
    for document in list_documents().values():
        items.append(
            {
                "id": f"document:{document['id']}",
                "record_type": "document",
                "record_id": document["id"],
                "sku": document.get("sku"),
                "location": document.get("location")
                or document.get("destination_location")
                or document.get("source_location"),
                "ticket_id": "",
                "document": _embed_text("document", document),
            }
        )
    for snapshot in list_snapshots():
        items.append(
            {
                "id": f"snapshot:{snapshot['snapshot_id']}",
                "record_type": "snapshot",
                "record_id": snapshot["snapshot_id"],
                "sku": snapshot.get("sku"),
                "location": snapshot.get("location"),
                "ticket_id": "",
                "document": _embed_text("snapshot", snapshot),
            }
        )
    return items


def seed_index(chroma_path: Path | None = None) -> dict[str, int]:
    """Rebuild the Chroma collection from SQLite warehouse records."""
    items = _index_items()
    embedder = get_embedder()
    client = _chroma_client(chroma_path)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    for offset in range(0, len(items), _EMBED_BATCH):
        batch = items[offset : offset + _EMBED_BATCH]
        embeddings = embedder.embed([item["document"] for item in batch])
        collection.add(
            ids=[item["id"] for item in batch],
            documents=[item["document"] for item in batch],
            embeddings=embeddings,
            metadatas=[
                {
                    "record_type": item["record_type"],
                    "record_id": item["record_id"],
                    "sku": _metadata_value(item["sku"]),
                    "location": _metadata_value(item["location"]),
                    "ticket_id": _metadata_value(item["ticket_id"]),
                }
                for item in batch
            ],
        )
    counts = {record_type: 0 for record_type in RECORD_TYPES}
    for item in items:
        counts[item["record_type"]] += 1
    return counts


def _hydrate(record_type: str, record_id: str) -> dict[str, Any] | None:
    if record_type == "ticket":
        return get_ticket(record_id)
    if record_type == "document":
        return get_document(record_id)
    if record_type == "ledger_event":
        return get_ledger_event(record_id)
    if record_type == "snapshot":
        return get_snapshot_record(record_id)
    return None


def _ensure_collection(chroma_path: Path | None = None):
    client = _chroma_client(chroma_path)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    if collection.count() == 0:
        seed_index(chroma_path)
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return collection


def search(
    query: str,
    record_type: str | None = None,
    n: int = DEFAULT_SEARCH_LIMIT,
    *,
    chroma_path: Path | None = None,
) -> list[dict[str, Any]]:
    if record_type and record_type not in RECORD_TYPES:
        raise ValueError(f"record_type must be one of {RECORD_TYPES}")
    collection = _ensure_collection(chroma_path)
    count = collection.count()
    if count == 0:
        return []
    limit = max(1, min(int(n), count, MAX_SEARCH_LIMIT))
    kwargs: dict[str, Any] = {
        "query_embeddings": get_embedder().embed([query]),
        "n_results": limit,
    }
    if record_type:
        kwargs["where"] = {"record_type": record_type}
    results = collection.query(**kwargs)
    ids = (results.get("ids") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    hits: list[dict[str, Any]] = []
    for index, chroma_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) else {}
        hydrated = _hydrate(str(metadata.get("record_type", "")), str(metadata.get("record_id", "")))
        if hydrated is None:
            continue
        hits.append(
            {
                "record_type": metadata.get("record_type"),
                "distance": distances[index] if index < len(distances) else None,
                "record": hydrated,
            }
        )
    return hits
