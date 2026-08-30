import json
from pathlib import Path

from warehouse_investigator import warehouse_data
from warehouse_investigator.warehouse_data import (
    WAREHOUSE_DATA_DIR,
    default_db_path,
    get_document,
    get_ticket,
    list_documents,
    list_ledger_events,
    list_snapshots,
    list_tickets,
    project_root,
    query_ledger,
    query_snapshots,
    seed,
)


def test_default_db_path_is_project_root_warehouse_db() -> None:
    assert default_db_path() == project_root() / "warehouse.db"
    assert default_db_path().parent / "pyproject.toml" == project_root() / "pyproject.toml"


def test_seed_writes_tickets_from_json(tmp_path: Path) -> None:
    db_path = tmp_path / "warehouse.db"

    seed(db_path)

    ticket = get_ticket("INC-001", db_path=db_path)
    assert ticket is not None
    assert ticket["sku"] == "SKU-RED-CHAIR"
    assert ticket["document_refs"] == ["TR-100"]
    assert list(list_tickets(db_path=db_path)) == [f"INC-{number:03d}" for number in range(1, 13)]


def test_seed_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "warehouse.db"
    seed(db_path)
    seed(db_path)

    expected_events = json.loads((WAREHOUSE_DATA_DIR / "ledger_events.json").read_text(encoding="utf-8"))
    assert len(list_tickets(db_path=db_path)) == 12
    assert len(list_ledger_events(db_path=db_path)) == len(expected_events)


def test_query_ledger_filters_and_sorts_newest_first(tmp_path: Path) -> None:
    db_path = tmp_path / "warehouse.db"
    seed(db_path)

    events = query_ledger(ticket_id="INC-001", db_path=db_path)
    assert events
    timestamps = [event["timestamp"] for event in events]
    assert timestamps == sorted(timestamps, reverse=True)
    assert any(event["sku"] != "SKU-RED-CHAIR" for event in events)


def test_ticket_ledger_query_ignores_sku_and_location(tmp_path: Path) -> None:
    db_path = tmp_path / "warehouse.db"
    seed(db_path)

    events = query_ledger(
        ticket_id="INC-006",
        sku="SKU-YELLOW-BENCH",
        location="SEA-01",
        db_path=db_path,
    )
    ids = {event["id"] for event in events}

    assert "EV-6001" in ids
    assert "EV-6002" in ids
    assert any(event["location"] == "PDX-01" for event in events)


def test_get_document_preserves_heterogeneous_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "warehouse.db"
    seed(db_path)

    transfer = get_document("TR-100", db_path=db_path)
    sales_order = get_document("SO-902", db_path=db_path)

    assert transfer is not None
    assert transfer["type"] == "transfer"
    assert transfer["received_at"] is None
    assert sales_order is not None
    assert sales_order["reservation_release_status"] == "failed"


def test_query_snapshots_returns_newest_first(tmp_path: Path) -> None:
    db_path = tmp_path / "warehouse.db"
    seed(db_path)

    snapshots = query_snapshots("SKU-RED-CHAIR", "SEA-01", db_path=db_path)
    assert snapshots[0]["snapshot_id"] == "SNAP-001-LATEST"
    assert snapshots[0]["captured_at"] == "2026-08-27T14:55:00Z"
    assert all(item["captured_at"] < snapshots[0]["captured_at"] for item in snapshots[1:])


def test_seed_does_not_store_evaluation_ground_truth(tmp_path: Path) -> None:
    db_path = tmp_path / "warehouse.db"
    seed(db_path)

    tickets = list_tickets(db_path=db_path)
    assert all("root_cause_code" not in ticket for ticket in tickets.values())
    documents = list_documents(db_path=db_path)
    snapshots = list_snapshots(db_path=db_path)
    assert documents
    assert len(snapshots) > len(tickets)


def test_connect_seeds_missing_database(tmp_path: Path) -> None:
    db_path = tmp_path / "warehouse.db"
    assert not db_path.exists()

    connection = warehouse_data.connect(db_path)
    connection.close()

    assert db_path.exists()
    assert get_ticket("INC-001", db_path=db_path)["id"] == "INC-001"
