"""Technical Analysis Agent.

Determines the main trend on the 1H timeframe, looks for an entry setup on the
15m timeframe, and proposes a direction with an ATR-based stop loss and target.
It emits the ``technical_score``, ``trend_score`` and ``volume_score`` consumed
by the Decision Agent.

Like every agent it is analysis-only: it never places orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from risk.models import Direction
from .base import BaseAgent, Signal
from .candles import Candle, closes, highs, lows, volumes
from . import indicators as ind


class Trend(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    SIDEWAYS = "SIDEWAYS"


@dataclass(frozen=True)
class TechnicalConfig:
    # 1H trend
    trend_fast: int = 20
    trend_slow: int = 50
    # 15m setup
    setup_fast: int = 9
    setup_slow: int = 21
    rsi_period: int = 14
    atr_period: int = 14
    # stop / target
    atr_stop_mult: float = 1.5
    reward_risk: float = 2.0
    # support/resistance and volume look-back
    sr_lookback: int = 20
    volume_lookback: int = 20
    # minimum normalized EMA separation to call a directional trend
    min_trend_strength: float = 0.15


@dataclass(frozen=True)
class TechnicalSignal:
    symbol: str
    trend: Trend
    direction: Direction | None
    trend_score: float
    technical_score: float
    volume_score: float
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    support: float | None = None
    resistance: float | None = None
    rationale: str = ""
    indicators: dict[str, float] = field(default_factory=dict)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _dir_score(diff: float, scale: float) -> float:
    """Map a signed difference to ``[0, 1]`` (0.5 at neutral, 1.0 at +scale)."""

    if scale <= 0:
        scale = abs(diff) or 1.0
    return _clamp(0.5 + diff / (2.0 * scale))


def _rsi_score(rsi_value: float, direction: Direction) -> float:
    if direction is Direction.LONG:
        base = _clamp((rsi_value - 40.0) / 20.0)
        if rsi_value > 75.0:  # fade overbought
            base *= _clamp((90.0 - rsi_value) / 15.0)
        return base
    base = _clamp((60.0 - rsi_value) / 20.0)
    if rsi_value < 25.0:  # fade oversold
        base *= _clamp((rsi_value - 10.0) / 15.0)
    return base


class TechnicalAnalysisAgent(BaseAgent):
    """Multi-timeframe technical analysis (1H trend + 15m timing)."""

    name = "technical_analysis"

    def __init__(self, config: TechnicalConfig | None = None) -> None:
        self._cfg = config or TechnicalConfig()

    # -- BaseAgent interface ----------------------------------------------

    def analyze(self, context: dict[str, Any]) -> Signal:
        """Return a :class:`Signal` carrying the technical score.

        ``context`` must contain ``candles_1h``, ``candles_15m`` and ``symbol``.
        """

        result = self.analyze_full(
            symbol=context.get("symbol", ""),
            candles_1h=context["candles_1h"],
            candles_15m=context["candles_15m"],
        )
        return Signal(
            self.name,
            result.technical_score,
            result.rationale,
            metadata={
                "direction": result.direction.value if result.direction else None,
                "trend": result.trend.value,
                "trend_score": result.trend_score,
                "volume_score": result.volume_score,
                "stop_loss": result.stop_loss,
                "take_profit": result.take_profit,
            },
        )

    # -- rich analysis -----------------------------------------------------

    def analyze_full(
        self,
        *,
        symbol: str,
        candles_1h: Sequence[Candle],
        candles_15m: Sequence[Candle],
        config: TechnicalConfig | None = None,
    ) -> TechnicalSignal:
        # A per-call config (e.g. a per-bucket strategy profile) overrides the
        # agent's default.
        cfg = config or self._cfg

        if (
            len(candles_1h) < cfg.trend_slow + 1
            or len(candles_15m) < max(cfg.setup_slow, cfg.rsi_period, cfg.atr_period) + 1
        ):
            return TechnicalSignal(
                symbol=symbol,
                trend=Trend.SIDEWAYS,
                direction=None,
                trend_score=0.0,
                technical_score=0.0,
                volume_score=0.0,
                rationale="insufficient candle history",
            )

        trend, trend_score, trend_ind = self._classify_trend(candles_1h, cfg)
        direction = {
            Trend.UP: Direction.LONG,
            Trend.DOWN: Direction.SHORT,
            Trend.SIDEWAYS: None,
        }[trend]

        c15 = closes(candles_15m)
        ema_f = ind.latest(ind.ema(c15, cfg.setup_fast))
        ema_s = ind.latest(ind.ema(c15, cfg.setup_slow))
        rsi_v = ind.latest(ind.rsi(c15, cfg.rsi_period))
        _, _, hist = ind.macd(c15)
        macd_hist = ind.latest(hist)
        atr15 = ind.latest(ind.atr(candles_15m, cfg.atr_period))
        entry = c15[-1]

        support = min(lows(candles_15m)[-cfg.sr_lookback :])
        resistance = max(highs(candles_15m)[-cfg.sr_lookback :])
        volume_score = self._volume_score(candles_15m, cfg)

        base_ind = {
            "ema_fast_15m": float(ema_f or 0.0),
            "ema_slow_15m": float(ema_s or 0.0),
            "rsi_15m": float(rsi_v or 0.0),
            "macd_hist_15m": float(macd_hist or 0.0),
            "atr_15m": float(atr15 or 0.0),
            **trend_ind,
        }

        # No tradable setup without a directional 1H trend.
        if direction is None or atr15 is None or atr15 <= 0:
            return TechnicalSignal(
                symbol=symbol,
                trend=trend,
                direction=None,
                trend_score=trend_score,
                technical_score=0.0,
                volume_score=volume_score,
                support=support,
                resistance=resistance,
                rationale=f"no setup (trend={trend.value})",
                indicators=base_ind,
            )

        sign = 1.0 if direction is Direction.LONG else -1.0
        comp_trend15 = _dir_score(sign * ((ema_f or 0.0) - (ema_s or 0.0)), atr15)
        comp_price = _dir_score(sign * (entry - (ema_f or entry)), atr15)
        comp_macd = _dir_score(sign * (macd_hist or 0.0), atr15 * 0.5)
        comp_rsi = _rsi_score(rsi_v if rsi_v is not None else 50.0, direction)
        technical_score = round(
            0.30 * comp_trend15
            + 0.30 * comp_price
            + 0.25 * comp_macd
            + 0.15 * comp_rsi,
            6,
        )

        stop, target = self._stop_and_target(entry, atr15, direction, cfg)

        return TechnicalSignal(
            symbol=symbol,
            trend=trend,
            direction=direction,
            trend_score=trend_score,
            technical_score=technical_score,
            volume_score=volume_score,
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
            support=support,
            resistance=resistance,
            rationale=(
                f"{direction.value} on {trend.value} 1H trend; "
                f"tech={technical_score:.2f} vol={volume_score:.2f}"
            ),
            indicators=base_ind,
        )

    # -- internals ---------------------------------------------------------

    def _classify_trend(
        self, candles_1h: Sequence[Candle], cfg: TechnicalConfig
    ) -> tuple[Trend, float, dict[str, float]]:
        c = closes(candles_1h)
        ema_fast = ind.latest(ind.ema(c, cfg.trend_fast)) or c[-1]
        ema_slow = ind.latest(ind.ema(c, cfg.trend_slow)) or c[-1]
        atr1h = ind.latest(ind.atr(candles_1h, cfg.atr_period)) or 0.0
        last = c[-1]

        sep = ema_fast - ema_slow
        scale = (2.0 * atr1h) if atr1h > 0 else (abs(sep) or 1.0)
        strength = _clamp(abs(sep) / scale)

        ind_out = {
            "ema_fast_1h": float(ema_fast),
            "ema_slow_1h": float(ema_slow),
            "atr_1h": float(atr1h),
        }
        # A directional trend needs EMA alignment, price on the right side and
        # a separation that clears the minimum-strength gate.
        if strength >= cfg.min_trend_strength:
            if ema_fast > ema_slow and last > ema_fast:
                return Trend.UP, strength, ind_out
            if ema_fast < ema_slow and last < ema_fast:
                return Trend.DOWN, strength, ind_out
        return Trend.SIDEWAYS, 0.0, ind_out

    def _volume_score(
        self, candles_15m: Sequence[Candle], cfg: TechnicalConfig
    ) -> float:
        vols = volumes(candles_15m)
        window = vols[-cfg.volume_lookback :]
        avg = sum(window) / len(window) if window else 0.0
        if avg <= 0:
            return 0.0
        ratio = vols[-1] / avg
        # ratio 1.0 -> 0.5, ratio >= 2.0 -> 1.0
        return _clamp(ratio / 2.0)

    def _stop_and_target(
        self, entry: float, atr15: float, direction: Direction, cfg: TechnicalConfig
    ) -> tuple[float, float]:
        risk = cfg.atr_stop_mult * atr15
        if direction is Direction.LONG:
            stop = entry - risk
            target = entry + cfg.reward_risk * risk
        else:
            stop = entry + risk
            target = entry - cfg.reward_risk * risk
        return stop, target
