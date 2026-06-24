"""Dashboard and reporting surface.

A J.A.R.V.I.S.-style HUD that renders a shadow run into a single self-contained
HTML page (no server, no external dependencies).
"""

from .hud import render_dashboard, report_to_data, write_dashboard

__all__ = ["render_dashboard", "report_to_data", "write_dashboard"]
