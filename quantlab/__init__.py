"""QuantLab - Quantitative Trading Pipeline

Integrates Qlib + Kronos + RD-Agent for A-share T+1 trading.
"""

__version__ = "0.1.0"

# Fix qlib import shadowing when running from project root (qlib/ submodule
# directory shadows the pip-installed qlib package). Must run before any
# other quantlab module imports qlib.
import quantlab._compat  # noqa: F401
