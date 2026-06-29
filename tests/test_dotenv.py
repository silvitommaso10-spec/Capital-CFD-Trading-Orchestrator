"""Tests for the dependency-free .env loader."""

from __future__ import annotations

import os

from app.env import load_dotenv


def test_loads_keys_into_environ(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CAPITAL_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "\n"
        "CAPITAL_API_KEY=abc123\n"
        "export CAPITAL_IDENTIFIER=user@example.com\n"
        'CAPITAL_API_PASSWORD="quoted secret"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert load_dotenv() is True
    assert os.environ["CAPITAL_API_KEY"] == "abc123"
    assert os.environ["CAPITAL_IDENTIFIER"] == "user@example.com"
    assert os.environ["CAPITAL_API_PASSWORD"] == "quoted secret"


def test_missing_file_returns_false(tmp_path) -> None:
    assert load_dotenv(tmp_path / "nope.env") is False


def test_does_not_override_existing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CAPITAL_API_KEY", "already-set")
    env = tmp_path / ".env"
    env.write_text("CAPITAL_API_KEY=from-file\n", encoding="utf-8")
    load_dotenv(env)
    assert os.environ["CAPITAL_API_KEY"] == "already-set"
    load_dotenv(env, override=True)
    assert os.environ["CAPITAL_API_KEY"] == "from-file"
