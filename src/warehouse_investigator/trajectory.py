from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any


class TrajectoryLogger:
    def __init__(self, ticket_id: str, output_dir: Path | None) -> None:
        self.ticket_id = ticket_id
        self.output_dir = output_dir
        self.started_at = datetime.now(UTC).isoformat()
        self.started_perf = perf_counter()
        self.events: list[dict[str, Any]] = []

    def add(self, event_type: str, **details: Any) -> None:
        self.events.append({"type": event_type, "elapsed_ms": round((perf_counter() - self.started_perf) * 1000), **details})

    @property
    def elapsed_ms(self) -> int:
        return round((perf_counter() - self.started_perf) * 1000)

    def save(self, result: dict[str, Any] | None = None, error: str | None = None) -> Path | None:
        if self.output_dir is None:
            return None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = self.output_dir / f"{self.ticket_id}_{timestamp}.json"
        payload = {
            "ticket_id": self.ticket_id,
            "started_at": self.started_at,
            "duration_ms": round((perf_counter() - self.started_perf) * 1000),
            "events": self.events,
            "result": result,
            "error": error,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path
