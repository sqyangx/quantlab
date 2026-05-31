"""TradingAgents-style post-selection analysis.

This package is intentionally independent from Kronos experiments and Model-A
training code. It consumes an already-built candidate pool and enriches it with
market, financial, announcement, news, and sentiment evidence.
"""

from .core import run_analysis
from .llm_prompts import ANALYSIS_DIMENSIONS, build_stock_analysis_messages

__all__ = ["ANALYSIS_DIMENSIONS", "build_stock_analysis_messages", "run_analysis"]
