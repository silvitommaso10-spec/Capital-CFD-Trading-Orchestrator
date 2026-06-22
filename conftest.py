"""Ensures the repository root is importable so tests can import the
top-level packages (app, capital, risk, agents, execution, backtesting)."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
