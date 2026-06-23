"""Persistent audit log (JSONL).

Each audit record is appended as one JSON object per line. The orchestrator
uses an audit sink to honour the rule that a trade must not proceed if its
pre-trade audit record cannot be saved: if the write raises, the pre-trade
gate sets ``audit_log_ok=False`` and the Risk Engine rejects the trade.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlAuditSink:
    """Append-only JSON Lines audit sink.

    Callable: ``sink(record)`` writes one line and flushes. A write failure
    raises, which (for the pre-trade record) blocks the trade.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def __call__(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, default=str, ensure_ascii=False)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()


def load_audit_log(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSONL audit file back into a list of records."""

    p = Path(path)
    if not p.exists():
        return []
    records: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
