"""Daily Report Agent.

Summarizes a batch of pipeline runs into a structured daily report for the
dashboard and email. Reporting only — it never trades.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Any, Sequence

from app.orchestrator import PipelineResult, PipelineState


@dataclass(frozen=True)
class DailyReport:
    date: str
    total: int
    by_state: dict[str, int]
    executed: list[dict[str, Any]] = field(default_factory=list)
    account: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "total": self.total,
            "by_state": self.by_state,
            "executed": self.executed,
            "account": self.account,
        }


class DailyReportAgent:
    """Builds a :class:`DailyReport` from pipeline results."""

    name = "daily_report"

    def build(
        self,
        results: Sequence[PipelineResult],
        *,
        report_date: date_cls | str | None = None,
        account: dict[str, Any] | None = None,
    ) -> DailyReport:
        counts: Counter[str] = Counter(r.state.value for r in results)
        # Ensure every state appears (zero-filled) for stable reporting.
        by_state = {state.value: counts.get(state.value, 0) for state in PipelineState}

        executed: list[dict[str, Any]] = []
        for r in results:
            if r.state is PipelineState.EXECUTED and r.order is not None:
                pos = r.order.simulated_position
                executed.append(
                    {
                        "symbol": r.symbol,
                        "direction": pos.direction.value if pos else None,
                        "size": pos.size if pos else None,
                        "entry": pos.entry_price if pos else None,
                        "final_score": r.decision.final_score,
                    }
                )

        if report_date is None:
            report_date = date_cls.today()
        date_str = report_date.isoformat() if isinstance(report_date, date_cls) else str(report_date)

        return DailyReport(
            date=date_str,
            total=len(results),
            by_state=by_state,
            executed=executed,
            account=account,
        )
