"""Tests for the J.A.R.V.I.S. HUD dashboard."""

from __future__ import annotations

from datetime import datetime, timezone

from app.ai_director import AIDirector
from app.config import load_config
from app.llm import MockLLMClient
from app.shadow import ShadowRunner, SyntheticDataSource
from dashboard.hud import render_dashboard, report_to_data, write_dashboard

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _run(**kwargs):
    config = load_config()
    runner = ShadowRunner(config, SyntheticDataSource(config), **kwargs)
    return runner.run(now=NOW)


def test_report_to_data_extracts_symbols() -> None:
    run = _run()
    data = report_to_data(run)
    assert data["mode"] == "SHADOW"
    assert len(data["symbols"]) == 5
    sym = data["symbols"][0]
    assert {"symbol", "state", "final_score", "direction", "scores"} <= sym.keys()
    assert "equity" in data


def test_render_contains_hud_markers() -> None:
    html = render_dashboard(report_to_data(_run()))
    assert "<!doctype html>" in html
    assert "J.A.R.V.I.S." in html
    assert "reactor" in html  # arc reactor element
    assert "US500" in html
    assert "READ" in html  # read-only badge
    assert html.strip().endswith("</html>")


def test_render_includes_director_briefing() -> None:
    run = _run(ai_director=AIDirector(MockLLMClient(canned="All clear, sir.")))
    html = render_dashboard(report_to_data(run))
    assert "AI DIRECTOR" in html
    assert "All clear, sir." in html


def test_write_dashboard_creates_file(tmp_path) -> None:
    out = write_dashboard(_run(), tmp_path / "hud" / "index.html")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "J.A.R.V.I.S." in text and "GOLD" in text


def test_render_escapes_briefing_html() -> None:
    run = _run(ai_director=AIDirector(MockLLMClient(canned="<script>evil()</script>")))
    html = render_dashboard(report_to_data(run))
    assert "<script>evil()" not in html
    assert "&lt;script&gt;" in html
