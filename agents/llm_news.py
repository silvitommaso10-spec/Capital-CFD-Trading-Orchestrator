"""LLM-backed news interpreter.

Turns unstructured news / macro text into structured :class:`MacroEvent`
objects that feed the deterministic News Macro Agent. The LLM only *reads* and
*classifies* text — the trading decision stays deterministic and auditable.

If no real LLM is configured (offline / no API key), the interpreter returns no
events and the pipeline simply runs without LLM-derived news.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Sequence

from app.config import NewsConfig
from app.llm import LLMClient
from app.logging_utils import get_logger
from .news_macro import Impact, MacroEvent

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a financial macro-news classifier. You read news text and extract "
    "discrete macro/economic events. You never give trading advice and never "
    "decide whether to trade — you only classify. Output strictly matches the "
    "provided JSON schema."
)


def _schema(categories: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["events"],
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["category", "sentiment", "impact", "confirmed", "title"],
                    "properties": {
                        "category": {"type": "string", "enum": list(categories)},
                        # bullish positive, bearish negative, in [-1, 1]
                        "sentiment": {"type": "number"},
                        "impact": {"type": "string", "enum": ["high", "medium", "low"]},
                        "confirmed": {"type": "boolean"},
                        "title": {"type": "string"},
                    },
                },
            }
        },
    }


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class LLMNewsInterpreter:
    """Extract structured macro events from text via an LLM."""

    def __init__(self, llm: LLMClient, config: NewsConfig) -> None:
        self._llm = llm
        self._cfg = config

    def interpret(
        self, text: str, now: datetime | None = None
    ) -> list[MacroEvent]:
        if not text.strip():
            return []
        now = now or datetime.now(timezone.utc)
        categories = self._cfg.tracked_categories
        prompt = (
            "Extract macro/economic events from the news text below. Only use "
            f"these categories: {', '.join(categories)}. For each event give a "
            "sentiment in [-1, 1] (bullish positive, bearish negative), an "
            "impact (high/medium/low), and whether it is confirmed (an actual "
            "release/decision) or unconfirmed (rumor/expectation). If there are "
            "no relevant events, return an empty list.\n\nNEWS:\n" + text
        )

        try:
            raw = self._llm.complete(
                prompt=prompt,
                system=SYSTEM_PROMPT,
                max_tokens=2000,
                json_schema=_schema(categories),
            )
            data = json.loads(raw) if raw.strip() else {"events": []}
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("news interpretation failed to parse: %s", exc)
            return []
        except Exception as exc:  # noqa: BLE001 - never let the LLM break the pipeline
            logger.warning("news interpretation error: %s", exc)
            return []

        events: list[MacroEvent] = []
        for item in data.get("events", []):
            category = str(item.get("category", ""))
            if category not in categories:
                continue
            try:
                impact = Impact(str(item.get("impact", "medium")).lower())
            except ValueError:
                impact = Impact.MEDIUM
            events.append(
                MacroEvent(
                    timestamp=now,
                    category=category,
                    impact=impact,
                    sentiment=_clamp(float(item.get("sentiment", 0.0) or 0.0)),
                    confirmed=bool(item.get("confirmed", True)),
                    title=str(item.get("title", "")),
                )
            )
        return events
