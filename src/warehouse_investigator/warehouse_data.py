"""Load model-visible warehouse records from SQLite, seeded from operational JSON."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


WAREHOUSE_DATA_DIR = Path(__file__).parent / "data" / "warehouse"

_SCHEMA = """
CREATE TABLE tickets (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    sku TEXT NOT NULL,
    location TEXT NOT NULL,
    reported_at TEXT NOT NULL,
    expected_quantity INTEGER NOT NULL,
    observed_quantity INTEGER NOT NULL,
    document_refs TEXT NOT NULL,
    notes TEXT NOT NULL,
    investigation_window_start TEXT NOT NULL
);

CREATE TABLE ledger_events (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    sku TEXT NOT NULL,
    location TEXT NOT NULL,
    event_type TEXT NOT NULL,
    quantity_delta INTEGER NOT NULL,
    document_id TEXT,
    state TEXT NOT NULL
);

CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    sku TEXT,
    payload TEXT NOT NULL
);

CREATE TABLE snapshots (
    snapshot_id TEXT PRIMARY KEY,
    sku TEXT NOT NULL,
    location TEXT NOT NULL,
    physical_quantity INTEGER NOT NULL,
    reserved_quantity INTEGER NOT NULL,
    available_quantity INTEGER NOT NULL,
    captured_at TEXT NOT NULL
);

CREATE INDEX idx_ledger_ticket ON ledger_events(ticket_id);
CREATE INDEX idx_ledger_sku ON ledger_events(sku);
CREATE INDEX idx_ledger_location ON ledger_events(location);
CREATE INDEX idx_snapshots_sku_location ON snapshots(sku, location);
"""

_override_db_path: Path | None = None


def project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists():
            return parent
    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists():
        return cwd
    raise FileNotFoundError("Could not find project root containing pyproject.toml")


def default_db_path() -> Path:
    return project_root() / "warehouse.db"


def resolve_db_path(db_path: Path | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    if _override_db_path is not None:
        return _override_db_path
    return default_db_path()


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


def seed(db_path: Path | None = None, data_dir: Path | None = None) -> Path:
    """Rebuild the warehouse SQLite database from the operational JSON datasets."""
    path = resolve_db_path(db_path)
    source = data_dir or WAREHOUSE_DATA_DIR
    tickets = _load_records("tickets", source)
    ledger_events = _load_records("ledger_events", source)
    documents = _load_records("documents", source)
    snapshots = _load_records("snapshots", source)
    _index_unique(tickets, "id", "tickets")
    _index_unique(ledger_events, "id", "ledger_events")
    _index_unique(documents, "id", "documents")
    _index_unique(snapshots, "snapshot_id", "snapshots")

    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            DROP TABLE IF EXISTS tickets;
            DROP TABLE IF EXISTS ledger_events;
            DROP TABLE IF EXISTS documents;
            DROP TABLE IF EXISTS snapshots;
            """
        )
        connection.executescript(_SCHEMA)
        connection.executemany(
            """
            INSERT INTO tickets (
                id, title, sku, location, reported_at, expected_quantity,
                observed_quantity, document_refs, notes, investigation_window_start
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    ticket["id"],
                    ticket["title"],
                    ticket["sku"],
                    ticket["location"],
                    ticket["reported_at"],
                    ticket["expected_quantity"],
                    ticket["observed_quantity"],
                    json.dumps(ticket["document_refs"]),
                    ticket["notes"],
                    ticket["investigation_window_start"],
                )
                for ticket in tickets
            ],
        )
        connection.executemany(
            """
            INSERT INTO ledger_events (
                id, ticket_id, timestamp, sku, location, event_type,
                quantity_delta, document_id, state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    event["id"],
                    event["ticket_id"],
                    event["timestamp"],
                    event["sku"],
                    event["location"],
                    event["event_type"],
                    event["quantity_delta"],
                    event.get("document_id"),
                    event["state"],
                )
                for event in ledger_events
            ],
        )
        connection.executemany(
            "INSERT INTO documents (id, type, sku, payload) VALUES (?, ?, ?, ?)",
            [
                (document["id"], document["type"], document.get("sku"), json.dumps(document))
                for document in documents
            ],
        )
        connection.executemany(
            """
            INSERT INTO snapshots (
                snapshot_id, sku, location, physical_quantity,
                reserved_quantity, available_quantity, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot["snapshot_id"],
                    snapshot["sku"],
                    snapshot["location"],
                    snapshot["physical_quantity"],
                    snapshot["reserved_quantity"],
                    snapshot["available_quantity"],
                    snapshot["captured_at"],
                )
                for snapshot in snapshots
            ],
        )
        connection.commit()
    return path


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    if not path.exists():
        seed(path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _ticket_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "sku": row["sku"],
        "location": row["location"],
        "reported_at": row["reported_at"],
        "expected_quantity": row["expected_quantity"],
        "observed_quantity": row["observed_quantity"],
        "document_refs": json.loads(row["document_refs"]),
        "notes": row["notes"],
        "investigation_window_start": row["investigation_window_start"],
    }


def _ledger_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "ticket_id": row["ticket_id"],
        "timestamp": row["timestamp"],
        "sku": row["sku"],
        "location": row["location"],
        "event_type": row["event_type"],
        "quantity_delta": row["quantity_delta"],
        "document_id": row["document_id"],
        "state": row["state"],
    }


def _snapshot_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "sku": row["sku"],
        "location": row["location"],
        "physical_quantity": row["physical_quantity"],
        "reserved_quantity": row["reserved_quantity"],
        "available_quantity": row["available_quantity"],
        "captured_at": row["captured_at"],
        "snapshot_id": row["snapshot_id"],
    }


def get_ticket(ticket_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        row = connection.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return _ticket_from_row(row) if row else None


def list_tickets(*, db_path: Path | None = None) -> dict[str, dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute("SELECT * FROM tickets ORDER BY id").fetchall()
    return {row["id"]: _ticket_from_row(row) for row in rows}


def query_ledger(
    ticket_id: str | None = None,
    sku: str | None = None,
    location: str | None = None,
    *,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[str] = []
    if ticket_id:
        clauses.append("ticket_id = ?")
        params.append(ticket_id)
    elif sku:
        clauses.append("sku = ?")
        params.append(sku)
    if location:
        clauses.append("location = ?")
        params.append(location)
    sql = "SELECT * FROM ledger_events"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY timestamp DESC"
    with connect(db_path) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [_ledger_from_row(row) for row in rows]


def get_ledger_event(event_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        row = connection.execute("SELECT * FROM ledger_events WHERE id = ?", (event_id,)).fetchone()
    return _ledger_from_row(row) if row else None


def list_ledger_events(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute("SELECT * FROM ledger_events ORDER BY timestamp DESC").fetchall()
    return [_ledger_from_row(row) for row in rows]


def get_document(document_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        row = connection.execute("SELECT payload FROM documents WHERE id = ?", (document_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def list_documents(*, db_path: Path | None = None) -> dict[str, dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute("SELECT id, payload FROM documents ORDER BY id").fetchall()
    return {row["id"]: json.loads(row["payload"]) for row in rows}


def get_snapshot_record(snapshot_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
    return _snapshot_from_row(row) if row else None


def query_snapshots(sku: str, location: str, *, db_path: Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT * FROM snapshots
            WHERE sku = ? AND location = ?
            ORDER BY captured_at DESC
            """,
            (sku, location),
        ).fetchall()
    return [_snapshot_from_row(row) for row in rows]


def list_snapshots(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute("SELECT * FROM snapshots ORDER BY captured_at DESC").fetchall()
    return [_snapshot_from_row(row) for row in rows]
