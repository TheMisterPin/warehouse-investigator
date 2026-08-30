"""Rebuild warehouse.db and the Chroma index at the project root."""

from .index import seed_index
from .warehouse_data import seed as seed_database


def main() -> None:
    db_path = seed_database()
    counts = seed_index()
    indexed = sum(counts.values())
    print(f"Seeded {db_path}")
    print(f"Indexed {indexed} records into chroma ({counts})")


if __name__ == "__main__":
    main()
