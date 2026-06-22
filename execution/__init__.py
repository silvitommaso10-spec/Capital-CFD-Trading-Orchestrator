"""Order execution.

The :class:`~execution.order_manager.OrderManager` is the *only* component
permitted to act on orders, and only after the Risk Engine has approved a
trade. In this version no real orders are sent to the broker under any mode;
simulated modes route through the paper CFD simulator.
"""

from .order_manager import OrderManager, OrderResult

__all__ = ["OrderManager", "OrderResult"]
