"""Exception hierarchy for the orchestrator."""

from __future__ import annotations


class OrchestratorError(Exception):
    """Base class for all orchestrator errors."""


class ConfigError(OrchestratorError):
    """Raised when configuration is missing or invalid."""


class MissingCredentialsError(OrchestratorError):
    """Raised when required credentials are not present in the environment."""


class BrokerError(OrchestratorError):
    """Base class for broker/transport related errors."""


class AuthenticationError(BrokerError):
    """Raised when the broker rejects authentication."""


class SessionExpiredError(BrokerError):
    """Raised when a broker session token is no longer valid."""


class MarketNotFoundError(BrokerError):
    """Raised when a requested market/epic cannot be resolved."""


class RateLimitError(BrokerError):
    """Raised when the broker signals that we are being rate limited."""


class RiskRejectedError(OrchestratorError):
    """Raised when the Risk Engine rejects a trade proposal."""


class LiveTradingDisabledError(OrchestratorError):
    """Raised on any attempt to send a real (live) order.

    Live trading is hard-disabled in this version. This error guards every
    code path that could otherwise reach the broker with a real order.
    """


class AuditLogError(OrchestratorError):
    """Raised when an audit log entry cannot be persisted.

    A trade must never proceed if its audit trail cannot be saved.
    """
