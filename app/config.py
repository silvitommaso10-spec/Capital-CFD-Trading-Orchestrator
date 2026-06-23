"""Configuration loading.

Reads the YAML files under ``config/`` into typed dataclasses. No secrets are
ever read from these files; credentials come from the environment (see
:mod:`app.env`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError
from .modes import OperatingMode, parse_mode

# Repository root: app/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Expected a mapping at the top of {path}")
    return data


@dataclass(frozen=True)
class HttpConfig:
    timeout_seconds: float = 15.0
    max_retries: int = 3
    backoff_seconds: float = 2.0


@dataclass(frozen=True)
class BrokerConfig:
    name: str
    product: str
    mode: OperatingMode
    live_trading_enabled: bool
    rest_base_url: str
    ws_base_url: str
    api_key_var: str
    identifier_var: str
    password_var: str
    http: HttpConfig
    session_refresh_margin_seconds: int = 60

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "BrokerConfig":
        broker = raw.get("broker", raw)
        endpoints = broker.get("endpoints", {})
        creds = broker.get("credentials_env", {})
        http = broker.get("http", {})
        session = broker.get("session", {})
        return BrokerConfig(
            name=str(broker.get("name", "capital_com")),
            product=str(broker.get("product", "CFD")),
            mode=parse_mode(broker.get("mode")),
            # Live trading stays disabled regardless of this flag in v1.
            live_trading_enabled=False,
            rest_base_url=str(endpoints.get("rest_base_url", "")),
            ws_base_url=str(endpoints.get("ws_base_url", "")),
            api_key_var=str(creds.get("api_key_var", "CAPITAL_API_KEY")),
            identifier_var=str(creds.get("identifier_var", "CAPITAL_IDENTIFIER")),
            password_var=str(creds.get("password_var", "CAPITAL_API_PASSWORD")),
            http=HttpConfig(
                timeout_seconds=float(http.get("timeout_seconds", 15)),
                max_retries=int(http.get("max_retries", 3)),
                backoff_seconds=float(http.get("backoff_seconds", 2)),
            ),
            session_refresh_margin_seconds=int(
                session.get("refresh_margin_seconds", 60)
            ),
        )


@dataclass(frozen=True)
class RiskConfig:
    default_risk_per_trade: float
    max_risk_per_trade: float
    daily_soft_stop: float
    daily_hard_stop: float
    emergency_kill_switch: float
    max_open_positions: int
    max_positions_per_bucket: int
    min_reward_risk: float
    require_stop_loss: bool
    block_on_stale_data: bool
    block_on_high_spread: bool
    block_on_insufficient_margin: bool
    block_on_unconfirmed_conflicting_news: bool
    block_if_audit_log_fails: bool
    max_data_age_seconds: float
    max_spread: dict[str, float]

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "RiskConfig":
        r = raw.get("risk", raw)
        try:
            return RiskConfig(
                default_risk_per_trade=float(r["default_risk_per_trade"]),
                max_risk_per_trade=float(r["max_risk_per_trade"]),
                daily_soft_stop=float(r["daily_soft_stop"]),
                daily_hard_stop=float(r["daily_hard_stop"]),
                emergency_kill_switch=float(r["emergency_kill_switch"]),
                max_open_positions=int(r["max_open_positions"]),
                max_positions_per_bucket=int(r["max_positions_per_bucket"]),
                min_reward_risk=float(r["min_reward_risk"]),
                require_stop_loss=bool(r.get("require_stop_loss", True)),
                block_on_stale_data=bool(r.get("block_on_stale_data", True)),
                block_on_high_spread=bool(r.get("block_on_high_spread", True)),
                block_on_insufficient_margin=bool(
                    r.get("block_on_insufficient_margin", True)
                ),
                block_on_unconfirmed_conflicting_news=bool(
                    r.get("block_on_unconfirmed_conflicting_news", True)
                ),
                block_if_audit_log_fails=bool(
                    r.get("block_if_audit_log_fails", True)
                ),
                max_data_age_seconds=float(r.get("max_data_age_seconds", 30)),
                max_spread=dict(r.get("max_spread", {})),
            )
        except KeyError as exc:
            raise ConfigError(f"Missing required risk setting: {exc}") from exc


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    epic: str
    bucket: str
    quote_currency: str
    contract_size: float
    min_deal_size: float
    margin_factor: float
    max_spread: float


@dataclass(frozen=True)
class InstrumentsConfig:
    instruments: tuple[Instrument, ...]
    buckets: dict[str, str]

    def by_symbol(self, symbol: str) -> Instrument:
        for inst in self.instruments:
            if inst.symbol == symbol:
                return inst
        raise ConfigError(f"Unknown instrument symbol: {symbol}")

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "InstrumentsConfig":
        items: list[Instrument] = []
        for entry in raw.get("instruments", []):
            items.append(
                Instrument(
                    symbol=str(entry["symbol"]),
                    name=str(entry.get("name", entry["symbol"])),
                    epic=str(entry["epic"]),
                    bucket=str(entry["bucket"]),
                    quote_currency=str(entry.get("quote_currency", "USD")),
                    contract_size=float(entry.get("contract_size", 1.0)),
                    min_deal_size=float(entry.get("min_deal_size", 0.0)),
                    margin_factor=float(entry.get("margin_factor", 0.05)),
                    max_spread=float(entry.get("max_spread", 0.0)),
                )
            )
        buckets = {
            name: str(meta.get("description", ""))
            for name, meta in (raw.get("buckets", {}) or {}).items()
        }
        return InstrumentsConfig(instruments=tuple(items), buckets=buckets)


@dataclass(frozen=True)
class AppConfig:
    broker: BrokerConfig
    risk: RiskConfig
    instruments: InstrumentsConfig

    @property
    def mode(self) -> OperatingMode:
        return self.broker.mode


@dataclass(frozen=True)
class NewsConfig:
    conflict_lookback_minutes: int
    high_impact_blackout_minutes_before: int
    high_impact_blackout_minutes_after: int
    tracked_categories: tuple[str, ...]
    category_bucket_impact: dict[str, tuple[str, ...]]

    def buckets_for_category(self, category: str) -> tuple[str, ...]:
        return self.category_bucket_impact.get(category, ())

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "NewsConfig":
        n = raw.get("news", raw)
        impact = {
            str(cat): tuple(str(b) for b in buckets)
            for cat, buckets in (n.get("category_bucket_impact", {}) or {}).items()
        }
        return NewsConfig(
            conflict_lookback_minutes=int(n.get("conflict_lookback_minutes", 120)),
            high_impact_blackout_minutes_before=int(
                n.get("high_impact_blackout_minutes_before", 15)
            ),
            high_impact_blackout_minutes_after=int(
                n.get("high_impact_blackout_minutes_after", 15)
            ),
            tracked_categories=tuple(
                str(c) for c in (n.get("tracked_categories", []) or [])
            ),
            category_bucket_impact=impact,
        )


def load_news_config(config_dir: Path | str = CONFIG_DIR) -> NewsConfig:
    """Load the news/macro configuration from ``config_dir``."""

    return NewsConfig.from_dict(_load_yaml(Path(config_dir) / "news.yaml"))


def load_config(config_dir: Path | str = CONFIG_DIR) -> AppConfig:
    """Load broker, risk and instrument configuration from ``config_dir``."""

    base = Path(config_dir)
    broker = BrokerConfig.from_dict(_load_yaml(base / "broker.yaml"))
    risk = RiskConfig.from_dict(_load_yaml(base / "risk.yaml"))
    instruments = InstrumentsConfig.from_dict(_load_yaml(base / "instruments.yaml"))
    return AppConfig(broker=broker, risk=risk, instruments=instruments)
