"""AI Director — read-only advisory layer.

The AI Director reads the daily report and the audit trail and produces a
natural-language briefing: what happened, why decisions were made, anomalies to
watch, and *suggested* (never auto-applied) parameter adjustments.

Hard boundary: the Director is advisory only. It has no reference to the Order
Manager or the Risk Engine, cannot place or modify orders, and cannot change
configuration. Its output is text for a human to read.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from app.llm import LLMClient
from app.logging_utils import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are the advisory director of an automated CFD trading research system. "
    "You are READ-ONLY: you explain and advise, you never execute trades, never "
    "modify orders, and never change configuration. Given a daily report and an "
    "audit trail, produce a concise briefing covering: (1) a one-line summary of "
    "the day, (2) why notable decisions were made, (3) anomalies or risks worth "
    "a human's attention, (4) optional parameter suggestions clearly marked as "
    "SUGGESTIONS for human review. Be specific and grounded in the data; do not "
    "invent numbers. Never tell the system to trade automatically."
)


class AIDirector:
    """Generates an advisory daily briefing from report + audit data."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def brief(
        self,
        report: dict[str, Any],
        audit_log: Sequence[dict[str, Any]],
        max_audit_entries: int = 60,
    ) -> str:
        recent_audit = list(audit_log)[-max_audit_entries:]
        prompt = (
            "DAILY REPORT (JSON):\n"
            + json.dumps(report, default=str, indent=2)
            + "\n\nAUDIT TRAIL (most recent entries, JSON):\n"
            + json.dumps(recent_audit, default=str, indent=2)
            + "\n\nWrite the advisory briefing now."
        )
        try:
            text = self._llm.complete(
                prompt=prompt, system=SYSTEM_PROMPT, max_tokens=2000
            )
        except Exception as exc:  # noqa: BLE001 - advisory must never break a run
            logger.warning("AI Director briefing failed: %s", exc)
            return "(AI Director unavailable; no briefing generated.)"
        return text.strip() or "(No briefing produced.)"
