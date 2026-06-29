"""Environment variable handling for credentials and runtime settings.

Credentials are read *only* from the process environment. They are never
written back to disk, logged, or returned in ``repr`` output.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import MissingCredentialsError


def load_dotenv(path: str | Path = ".env", *, override: bool = False) -> bool:
    """Load ``KEY=VALUE`` lines from a ``.env`` file into the process environment.

    A tiny, dependency-free loader. Blank lines and ``#`` comments are ignored;
    surrounding single/double quotes are stripped; an optional leading
    ``export`` is allowed. Existing environment variables are preserved unless
    ``override`` is set. Returns ``True`` if the file existed.

    Secrets are loaded into the environment only — never logged or written back.
    """

    p = Path(path)
    if not p.exists():
        return False
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (len(value) >= 2) and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
    return True


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
