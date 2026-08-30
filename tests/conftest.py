from pathlib import Path

import pytest

from warehouse_investigator import warehouse_data
from warehouse_investigator.embeddings import HashEmbedder
from warehouse_investigator import index


@pytest.fixture(autouse=True)
def isolated_warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "warehouse.db"
    chroma_path = tmp_path / "chroma"
    monkeypatch.setattr(warehouse_data, "_override_db_path", db_path)
    monkeypatch.setattr(index, "_override_chroma_path", chroma_path)
    monkeypatch.setattr(index, "_override_embedder", HashEmbedder())
    return db_path
