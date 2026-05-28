"""Lightweight CSV runtime logger for evaluation data.

The main loop calls ``log_frame`` once per frame. Rows are queued with
``put_nowait`` and written by a background thread so camera processing is not
held up by disk I/O. If the queue fills, the logger drops rows rather than
blocking the robot loop.
"""

from __future__ import annotations

import csv
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RuntimeCsvLogger:
    """Non-blocking CSV logger for frame-level perception metrics."""

    FIELDNAMES = [
        "timestamp_utc",
        "fps",
        "processing_latency_ms",
        "raw_gesture",
        "raw_confidence",
        "debounced_command",
        "emitted_command",
        "routed_command",
        "current_mode",
    ]

    def __init__(
        self,
        log_dir: str | Path = "data/raw_logs",
        flush_every: int = 30,
        max_queue_size: int = 2048,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.path = self.log_dir / f"run_{stamp}.csv"

        self._flush_every = flush_every
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(max_queue_size)
        self._dropped_rows = 0
        self._thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._thread.start()

    @property
    def dropped_rows(self) -> int:
        return self._dropped_rows

    def log_frame(
        self,
        fps: float,
        processing_latency_ms: float,
        raw_gesture: str | None,
        raw_confidence: float,
        debounced_command: str | None,
        emitted_command: str | None,
        routed_command: str | None,
        current_mode: str,
    ) -> None:
        row = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "fps": f"{fps:.2f}",
            "processing_latency_ms": f"{processing_latency_ms:.2f}",
            "raw_gesture": raw_gesture or "",
            "raw_confidence": f"{raw_confidence:.3f}",
            "debounced_command": debounced_command or "",
            "emitted_command": emitted_command or "",
            "routed_command": routed_command or "",
            "current_mode": current_mode,
        }

        try:
            self._queue.put_nowait(row)
        except queue.Full:
            self._dropped_rows += 1

    def close(self) -> None:
        while True:
            try:
                self._queue.put_nowait(None)
                break
            except queue.Full:
                try:
                    self._queue.get_nowait()
                    self._dropped_rows += 1
                except queue.Empty:
                    pass
        self._thread.join(timeout=2.0)

    def _writer_loop(self) -> None:
        rows_since_flush = 0
        with self.path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self.FIELDNAMES)
            writer.writeheader()

            while True:
                row = self._queue.get()
                if row is None:
                    break

                writer.writerow(row)
                rows_since_flush += 1
                if rows_since_flush >= self._flush_every:
                    file.flush()
                    rows_since_flush = 0

            file.flush()
