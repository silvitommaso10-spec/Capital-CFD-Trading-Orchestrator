"""Tests for per-bucket strategy profiles."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents.candles import Candle
from agents.technical_analysis import TechnicalAnalysisAgent, TechnicalConfig
from app.config import StrategyConfig, StrategyProfile, load_strategy_config

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_default_profile_values() -> None:
    sc = load_strategy_config()
    default = sc.for_bucket("does_not_exist")  # unknown -> default
    assert default.atr_stop_mult == 1.5
    assert default.reward_risk == 2.0
    assert default.min_trend_strength == 0.15


def test_crypto_overrides_merge_with_default() -> None:
    sc = load_strategy_config()
    crypto = sc.for_bucket("crypto")
    # overridden
    assert crypto.atr_stop_mult == 2.2
    assert crypto.reward_risk == 2.2
    assert crypto.min_trend_strength == 0.20
    # inherited from default
    assert crypto.trend_fast == 20
    assert crypto.trend_slow == 50


def test_from_dict_ignores_unknown_keys() -> None:
    raw = {
        "strategy": {
            "default": {"atr_stop_mult": 1.0, "bogus": 99},
            "buckets": {"crypto": {"reward_risk": 3.0, "nonsense": 1}},
        }
    }
    sc = StrategyConfig.from_dict(raw)
    assert sc.default.atr_stop_mult == 1.0
    assert sc.for_bucket("crypto").reward_risk == 3.0
    assert not hasattr(sc.default, "bogus")


def test_technical_kwargs_build_technical_config() -> None:
    profile = StrategyProfile(atr_stop_mult=2.2, reward_risk=2.2)
    cfg = TechnicalConfig(**profile.technical_kwargs())
    assert cfg.atr_stop_mult == 2.2
    assert cfg.reward_risk == 2.2


def _uptrend(n: int, step: float, step_min: int) -> list[Candle]:
    return [
        Candle(BASE + timedelta(minutes=step_min * i), 100 + step * i,
               100 + step * i + 1, 100 + step * i - 1, 100 + step * i, 1000.0)
        for i in range(n)
    ]


def test_wider_stop_for_higher_atr_multiplier() -> None:
    agent = TechnicalAnalysisAgent()
    c1h = _uptrend(60, 1.0, 60)
    c15 = _uptrend(40, 0.5, 15)

    default_cfg = TechnicalConfig(atr_stop_mult=1.5)
    wide_cfg = TechnicalConfig(atr_stop_mult=2.2)

    base = agent.analyze_full(symbol="X", candles_1h=c1h, candles_15m=c15, config=default_cfg)
    wide = agent.analyze_full(symbol="X", candles_1h=c1h, candles_15m=c15, config=wide_cfg)

    base_dist = base.entry_price - base.stop_loss
    wide_dist = wide.entry_price - wide.stop_loss
    # same ATR, so stop distance scales with the multiplier
    assert wide_dist == pytest.approx(base_dist * (2.2 / 1.5))
