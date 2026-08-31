from __future__ import annotations

import sys
import threading
from time import perf_counter
from typing import TextIO


_SPINNER = "|/-\\"


def format_investigation_status(ticket_id: str, elapsed_s: float, frame: int = 0) -> str:
    spinner = _SPINNER[frame % len(_SPINNER)]
    return f"{spinner} Investigating {ticket_id}...  {elapsed_s:.1f}s"


class InvestigationProgress:
    """Live stderr status so a long investigation is visibly in progress."""

    def __init__(
        self,
        ticket_ids: list[str],
        stream: TextIO | None = None,
        live: bool | None = None,
        interval_seconds: float = 0.1,
    ) -> None:
        self.ticket_ids = ticket_ids
        self.stream = stream or sys.stderr
        self.live = self.stream.isatty() if live is None else live
        self.interval_seconds = interval_seconds
        self.current: str | None = None
        self.started_at: float | None = None
        self.frame = 0
        self.drawn = False
        self._stop = threading.Event()
        self._ticker: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if not self.live:
            return
        self.stream.write("\x1b[?25l")
        self.stream.flush()
        if self.interval_seconds > 0:
            self._ticker = threading.Thread(target=self._tick, name="investigation-progress", daemon=True)
            self._ticker.start()

    def mark_working(self, ticket_id: str) -> None:
        with self._lock:
            self.current = ticket_id
            self.started_at = perf_counter()
        if self.live:
            self.render()
            return
        self.stream.write(f"Investigating {ticket_id}...\n")
        self.stream.flush()

    def close(self) -> None:
        self._stop.set()
        if self._ticker is not None:
            self._ticker.join(timeout=0.2)
        if not self.live:
            return
        if self.drawn:
            self.stream.write("\r\x1b[2K")
        self.stream.write("\x1b[?25h")
        self.stream.flush()

    def render(self) -> None:
        if not self.live:
            return
        with self._lock:
            if self.current is None or self.started_at is None:
                return
            elapsed = perf_counter() - self.started_at
            line = format_investigation_status(self.current, elapsed, self.frame)
            self.frame += 1
        self.stream.write(f"\r\x1b[2K{line}")
        self.stream.flush()
        self.drawn = True

    def _tick(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            self.render()
