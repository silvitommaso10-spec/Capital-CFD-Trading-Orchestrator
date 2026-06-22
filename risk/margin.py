"""Position sizing and margin calculations for CFDs.

Leverage is never an objective. Position size is derived from capital, the
stop-loss distance and the per-trade risk budget, then validated against the
margin required to hold it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionSizing:
    """Result of a sizing calculation."""

    size: float                 # number of contracts/units
    risk_amount: float          # capital at risk if stop is hit (quote ccy)
    notional: float             # full notional exposure (quote ccy)
    required_margin: float      # margin needed to hold the position
    stop_distance: float        # price distance to stop

    @property
    def effective_leverage(self) -> float:
        if self.required_margin <= 0:
            return 0.0
        return self.notional / self.required_margin


class MarginCalculator:
    """Compute position size and margin from risk-first principles."""

    def required_margin(
        self, *, size: float, price: float, contract_size: float, margin_factor: float
    ) -> float:
        """Margin needed to hold ``size`` contracts at ``price``."""

        notional = abs(size) * price * contract_size
        return notional * margin_factor

    def size_for_risk(
        self,
        *,
        equity: float,
        risk_per_trade: float,
        entry_price: float,
        stop_loss: float,
        contract_size: float = 1.0,
        margin_factor: float = 0.05,
        min_deal_size: float = 0.0,
    ) -> PositionSizing:
        """Size a position so the loss at the stop equals the risk budget.

        ``risk_amount = equity * risk_per_trade`` and
        ``size = risk_amount / (stop_distance * contract_size)``.

        Raises ``ValueError`` for non-positive equity/risk or a zero stop
        distance (a stop loss is mandatory and must differ from entry).
        """

        if equity <= 0:
            raise ValueError("equity must be positive")
        if risk_per_trade <= 0:
            raise ValueError("risk_per_trade must be positive")

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            raise ValueError("stop distance must be positive (stop loss required)")

        risk_budget = equity * risk_per_trade
        raw_size = risk_budget / (stop_distance * contract_size)

        # Snap down to the broker's minimum deal-size increment when provided.
        size = raw_size
        if min_deal_size > 0:
            steps = int(raw_size / min_deal_size)
            size = steps * min_deal_size

        risk_amount = size * stop_distance * contract_size
        notional = size * entry_price * contract_size
        margin = self.required_margin(
            size=size,
            price=entry_price,
            contract_size=contract_size,
            margin_factor=margin_factor,
        )
        return PositionSizing(
            size=size,
            risk_amount=risk_amount,
            notional=notional,
            required_margin=margin,
            stop_distance=stop_distance,
        )
