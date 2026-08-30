from warehouse_investigator.tools import execute_tool
from warehouse_investigator.warehouse_data import project_root
from warehouse_investigator.index import default_chroma_path, seed_index, search


def test_default_chroma_path_is_project_root_chroma() -> None:
    assert default_chroma_path() == project_root() / "chroma"


def test_seed_index_embeds_all_warehouse_record_types() -> None:
    counts = seed_index()

    assert counts == {"ticket": 12, "ledger_event": 65, "document": 36, "snapshot": 36}


def test_search_finds_ticket_and_hydrates_the_record() -> None:
    seed_index()

    hits = search("INC-001", record_type="ticket")

    assert hits
    assert hits[0]["record_type"] == "ticket"
    assert hits[0]["record"]["id"] == "INC-001"
    assert "distance" in hits[0]
    assert hits[0]["record"]["sku"] == "SKU-RED-CHAIR"


def test_search_can_filter_to_documents() -> None:
    seed_index()

    hits = search("TR-100", record_type="document")

    assert hits
    assert all(hit["record_type"] == "document" for hit in hits)
    assert any(hit["record"]["id"] == "TR-100" for hit in hits)


def test_search_records_tool_requires_a_query() -> None:
    result = execute_tool("search_records", {})

    assert result == {"error": "search_records requires query"}


def test_search_records_tool_returns_matching_records() -> None:
    result = execute_tool("search_records", {"query": "INC-001", "record_type": "ticket", "n": 3})

    assert isinstance(result, list)
    assert result[0]["record"]["id"] == "INC-001"
    assert result[0]["record_type"] == "ticket"
