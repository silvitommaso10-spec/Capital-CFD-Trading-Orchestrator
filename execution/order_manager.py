"""Order Manager.

The single authorized point for acting on orders. Invariants enforced here:

1. A trade is processed only if the Risk Engine approved it.
2. No real broker order is ever sent in this version (live trading disabled).
3. In simulated modes (BACKTEST/SHADOW) orders route to the paper simulator.
4. In CAPITAL_DEMO/LIVE_DISABLED the manager refuses to send orders, because
   this milestone is strictly read-only against the broker.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.errors import LiveTradingDisabledError, RiskRejectedError
from app.logging_utils import get_logger
from app.modes import SIMULATED_MODES, OperatingMode, is_live_trading_enabled
from backtesting.paper_simulator import PaperCFDSimulator, SimulatedPosition
from risk.engine import RiskDecision
from risk.models import TradeProposal

logger = get_logger(__name__)


@dataclass(frozen=True)
class OrderResult:
    accepted: bool
    mode: OperatingMode
    detail: str
    simulated_position: SimulatedPosition | None = None


class OrderManager:
    """Routes approved trades; never sends a real order in this version."""

    def __init__(
        self,
        mode: OperatingMode,
        simulator: PaperCFDSimulator | None = None,
    ) -> None:
        self._mode = mode
        self._simulator = simulator

    def submit(
        self, proposal: TradeProposal, decision: RiskDecision
    ) -> OrderResult:
        # Invariant 1: must be approved by the Risk Engine.
        if not decision.approved:
            raise RiskRejectedError(
                "Order Manager refused a trade not approved by the Risk Engine: "
                + ", ".join(r.value for r in decision.reasons)
            )

        # Invariant 2: live trading is impossible.
        if is_live_trading_enabled(self._mode):  # pragma: no cover - always False
            raise LiveTradingDisabledError("Live trading is disabled.")

        # Invariant 3: simulated modes use the paper simulator.
        if self._mode in SIMULATED_MODES:
            if self._simulator is None or decision.sizing is None:
                raise RiskRejectedError(
                    "Simulator or sizing unavailable for a simulated order."
                )
            position = self._simulator.open_position(
                symbol=proposal.symbol,
                direction=proposal.direction,
                size=decision.sizing.size,
                price=proposal.entry_price,
                contract_size=proposal.contract_size,
                margin_factor=proposal.margin_factor,
                stop_loss=proposal.stop_loss,
                take_profit=proposal.take_profit,
            )
            logger.info(
                "paper order filled: %s %s size=%s",
                proposal.symbol,
                proposal.direction.value,
                decision.sizing.size,
            )
            return OrderResult(
                accepted=True,
                mode=self._mode,
                detail="paper fill",
                simulated_position=position,
            )

        # Invariant 4: read-only against the broker in this version.
        raise LiveTradingDisabledError(
            f"Order placement is not available in mode {self._mode.value}; "
            "this version is read-only against the broker."
        )
