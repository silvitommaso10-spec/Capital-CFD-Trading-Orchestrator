"""LLM client abstraction.

A thin, optional layer over a large language model. Two implementations:

- :class:`AnthropicLLMClient` — calls Claude (``claude-opus-4-8``) via the
  official ``anthropic`` SDK. The API key comes only from the environment
  (``ANTHROPIC_API_KEY``), consistent with the project's secrets policy.
- :class:`MockLLMClient` — deterministic, offline; used for tests and when no
  API key is configured.

The LLM is used only to turn unstructured text into structured analysis or
advisory commentary. Its output never reaches the Order Manager and never
overrides the deterministic Risk Engine — that boundary is enforced by the
callers (the News interpreter feeds the deterministic News Macro Agent; the
AI Director is read-only).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.errors import MissingCredentialsError
from app.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = "claude-opus-4-8"


class LLMClient(Protocol):
    """Minimal text-in/text-out interface."""

    def complete(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 4000,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        """Return the model's text response (JSON when ``json_schema`` is set)."""
        ...


class AnthropicLLMClient:
    """Claude-backed client. Requires the ``anthropic`` SDK and an API key."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key_var: str = "ANTHROPIC_API_KEY",
        effort: str = "low",
    ) -> None:
        try:
            import anthropic  # local import keeps the dependency optional
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise MissingCredentialsError(
                "The 'anthropic' package is required for AnthropicLLMClient"
            ) from exc

        key = (os.environ.get(api_key_var) or "").strip()
        if not key:
            raise MissingCredentialsError(
                f"Missing required environment variable: {api_key_var}"
            )
        self._client = anthropic.Anthropic(api_key=key)
        self._model = model
        self._effort = effort

    def complete(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 4000,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        output_config: dict[str, Any] = {"effort": self._effort}
        if json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": json_schema}

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "thinking": {"type": "adaptive"},
            "output_config": output_config,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        resp = self._client.messages.create(**kwargs)
        return "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )


@dataclass
class MockLLMClient:
    """Deterministic offline client.

    Returns ``canned`` for every call, or a queued response from ``responses``
    (consumed in order) when provided. Used in tests and when no real LLM is
    configured.
    """

    canned: str = ""
    responses: list[str] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 4000,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        self.calls.append({"prompt": prompt, "system": system})
        if self.responses:
            return self.responses.pop(0)
        return self.canned


def build_llm_client(prefer_real: bool = True) -> LLMClient:
    """Return the real client when possible, else the deterministic mock.

    The real client is used only when ``prefer_real`` is set, the ``anthropic``
    package is importable, and ``ANTHROPIC_API_KEY`` is present. Otherwise a
    :class:`MockLLMClient` is returned so the system runs unchanged offline.
    """

    if prefer_real and (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        try:
            return AnthropicLLMClient()
        except MissingCredentialsError as exc:  # pragma: no cover - env dependent
            logger.warning("falling back to MockLLMClient: %s", exc)
    return MockLLMClient()
