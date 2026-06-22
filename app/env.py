"""Environment variable handling for credentials and runtime settings.

Credentials are read *only* from the process environment. They are never
written back to disk, logged, or returned in ``repr`` output.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .errors import MissingCredentialsError


@dataclass(frozen=True)
class Credentials:
    """Capital.com demo credentials sourced from the environment.

    The ``__repr__`` is overridden so the secret values can never leak into a
    log line, traceback, or debugger output.
    """

    api_key: str = field(repr=False)
    identifier: str = field(repr=False)
    password: str = field(repr=False)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "Credentials(api_key=***, identifier=***, password=***)"


def load_credentials(
    *,
    api_key_var: str = "CAPITAL_API_KEY",
    identifier_var: str = "CAPITAL_IDENTIFIER",
    password_var: str = "CAPITAL_API_PASSWORD",
    environ: dict[str, str] | None = None,
) -> Credentials:
    """Load and validate credentials from the environment.

    Raises :class:`MissingCredentialsError` listing the missing variable names
    (never their values) when any required variable is absent or empty.
    """

    source = environ if environ is not None else dict(os.environ)
    missing: list[str] = []

    api_key = (source.get(api_key_var) or "").strip()
    identifier = (source.get(identifier_var) or "").strip()
    password = (source.get(password_var) or "").strip()

    if not api_key:
        missing.append(api_key_var)
    if not identifier:
        missing.append(identifier_var)
    if not password:
        missing.append(password_var)

    if missing:
        raise MissingCredentialsError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    return Credentials(api_key=api_key, identifier=identifier, password=password)


def get_env(name: str, default: str | None = None) -> str | None:
    """Thin wrapper around ``os.environ.get`` for non-secret settings."""

    return os.environ.get(name, default)
