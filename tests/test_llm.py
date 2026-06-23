"""Tests for the LLM abstraction, news interpreter and AI Director.

All tests run offline against MockLLMClient — no network, no API key.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from agents.llm_news import LLMNewsInterpreter
from agents.news_macro import Impact
from app.ai_director import AIDirector
from app.config import load_news_config
from app.llm import MockLLMClient, build_llm_client

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


# -- LLMClient -------------------------------------------------------------


def test_mock_client_returns_canned() -> None:
    client = MockLLMClient(canned="hello")
    assert client.complete(prompt="x") == "hello"
    assert client.calls[0]["prompt"] == "x"


def test_mock_client_queued_responses() -> None:
    client = MockLLMClient(responses=["a", "b"])
    assert client.complete(prompt="1") == "a"
    assert client.complete(prompt="2") == "b"
    assert client.complete(prompt="3") == ""  # falls back to canned ("")


def test_build_llm_client_offline_returns_mock(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = build_llm_client(prefer_real=True)
    assert isinstance(client, MockLLMClient)
    # explicit offline preference
    assert isinstance(build_llm_client(prefer_real=False), MockLLMClient)


# -- News interpreter ------------------------------------------------------


def make_interpreter(canned: str) -> LLMNewsInterpreter:
    return LLMNewsInterpreter(MockLLMClient(canned=canned), load_news_config())


def test_interpret_parses_events() -> None:
    payload = json.dumps({
        "events": [
            {"category": "inflation", "sentiment": 0.7, "impact": "high",
             "confirmed": True, "title": "CPI cooler than expected"},
            {"category": "central_bank", "sentiment": -0.4, "impact": "medium",
             "confirmed": False, "title": "Rumored hawkish hold"},
        ]
    })
    events = make_interpreter(payload).interpret("some news", now=NOW)
    assert len(events) == 2
    assert events[0].category == "inflation"
    assert events[0].impact is Impact.HIGH
    assert events[0].sentiment == 0.7
    assert events[0].confirmed is True
    assert events[0].timestamp == NOW
    assert events[1].confirmed is False


def test_interpret_skips_unknown_category() -> None:
    payload = json.dumps({"events": [
        {"category": "aliens", "sentiment": 1.0, "impact": "high",
         "confirmed": True, "title": "n/a"},
    ]})
    assert make_interpreter(payload).interpret("text", now=NOW) == []


def test_interpret_clamps_sentiment() -> None:
    payload = json.dumps({"events": [
        {"category": "rates", "sentiment": 5.0, "impact": "low",
         "confirmed": True, "title": "x"},
    ]})
    events = make_interpreter(payload).interpret("text", now=NOW)
    assert events[0].sentiment == 1.0


def test_interpret_bad_json_returns_empty() -> None:
    assert make_interpreter("not json").interpret("text", now=NOW) == []


def test_interpret_empty_text_returns_empty() -> None:
    assert make_interpreter("{}").interpret("   ", now=NOW) == []


# -- AI Director -----------------------------------------------------------


def test_director_returns_briefing() -> None:
    director = AIDirector(MockLLMClient(canned="Day summary: 3 trades, all sound."))
    text = director.brief(
        report={"date": "2026-06-01", "total": 5, "by_state": {"EXECUTED": 3}},
        audit_log=[{"symbol": "US500", "decision": "TRADE_CANDIDATE"}],
    )
    assert "Day summary" in text


def test_director_handles_empty_response() -> None:
    director = AIDirector(MockLLMClient(canned=""))
    text = director.brief(report={"total": 0}, audit_log=[])
    assert "No briefing" in text


def test_director_passes_report_and_audit_to_llm() -> None:
    mock = MockLLMClient(canned="ok")
    AIDirector(mock).brief(report={"total": 2}, audit_log=[{"symbol": "GOLD"}])
    # the prompt embeds both the report and the audit data
    prompt = mock.calls[0]["prompt"]
    assert "DAILY REPORT" in prompt and "AUDIT TRAIL" in prompt
    assert "GOLD" in prompt
