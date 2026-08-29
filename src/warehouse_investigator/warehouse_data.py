"""Load model-visible warehouse records from separated operational datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


WAREHOUSE_DATA_DIR = Path(__file__).parent / "data" / "warehouse"


def _load_records(name: str, data_dir: Path = WAREHOUSE_DATA_DIR) -> list[dict[str, Any]]:
    path = data_dir / f"{name}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(record, dict) for record in value):
        raise ValueError(f"Warehouse dataset {path} must contain a JSON array of objects")
    return value


def _index_unique(records: list[dict[str, Any]], key: str, dataset: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        value = record.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Record in {dataset} has no {key}")
        if value in indexed:
            raise ValueError(f"Duplicate {key} {value} in {dataset}")
        indexed[value] = record
    return indexed


TICKET_RECORDS = _load_records("tickets")
LEDGER_EVENTS = _load_records("ledger_events")
DOCUMENT_RECORDS = _load_records("documents")
SNAPSHOTS = _load_records("snapshots")

TICKETS = _index_unique(TICKET_RECORDS, "id", "tickets")
DOCUMENTS = _index_unique(DOCUMENT_RECORDS, "id", "documents")
_index_unique(LEDGER_EVENTS, "id", "ledger_events")

