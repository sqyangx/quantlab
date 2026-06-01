# QuantLab Trading Strategy Release

This folder is the GitHub-publishable trading strategy release package.

It contains a standalone TradingAgents-style analyst module, static UI pages, and release tooling. It intentionally excludes experiment folders, model weights, and raw daily trading debug outputs.

## Contents

- `frontend/tradingagents_modela_ui_20260501_20260529/`
  - Static SmartStock AI UI for the May 2026 demo range.
- `frontend/tradingagents_modela_ui_202606/`
  - June 2026 after-close Model-A release UI. Rebuilt after each new close signal.
- `data/tradingagents_modela_rerank_202606/`
  - June 2026 TradingAgents secondary analysis JSON/CSV/Markdown.
- `data/5min_modela_portfolio_backtest_202606/`
  - June 2026 account tracking files for generated Model-A signals.
- `src/quantlab/post_analysis/tradingagents/`
  - Standalone multi-agent analyst/reranking module.
  - It consumes a candidate pool and produces evidence-aware recommendations.
- `tools/backtest_selection_table_account.py`
  - Corrected capital-aware account backtest from an EXP047-style `selection_table.csv`.
- `tools/build_daily_selection_release.py`
  - Internal helper for building daily JSON/Markdown/CSV outputs. Generated `daily_results_2026` is not part of the GitHub release.
- `tools/build_tradingagents_ui.py`
  - Builds the static frontend from analysis and account outputs.

## Daily After-Close Model-A Release

Run this from the repository root after the 5-minute provider has the close data available:

```bash
/home/gpu/.conda/envs/asrlab/bin/python -u scripts/run_modela_daily_release_after_close.py \
  --date YYYY-MM-DD \
  --gpu 0
```

The command first runs the 5-minute first flow unless `--skip-first-flow` is passed, then writes monthly release artifacts:

```text
quantlab/trading_strategy_release/data/tradingagents_modela_rerank_YYYYMM/
quantlab/trading_strategy_release/data/5min_modela_portfolio_backtest_YYYYMM/
quantlab/trading_strategy_release/frontend/tradingagents_modela_ui_YYYYMM/
```

## Excluded From Release

Do not publish:

- `data/daily_results_2026/`
- model checkpoints, including `*.pt`, `*.pth`, `*.ckpt`
- Kronos `.npz` outputs
- qlib `.bin` providers
- experiment folders such as `quantlab/experiments`
- large local artifact directories `quantlab/01_*` through `quantlab/08_*`

## Model-A Account Result Used Here

Source selection table:

```text
quantlab/07_stock_selection_strategies/exp047_1500_modela_opt1_top5/selection_table.csv
```

Corrected account-level 2026 result:

```text
actual signal range: 2026-01-05 to 2026-05-25
signal groups: 91
executed groups: 46
skipped groups: 45
completed trades: 230
initial capital: 100000
end NAV: 271293.178814
total return: 171.293179%
max drawdown on exit NAV: -9.957699%
```

`daily_basket_returns.csv` must not be quoted as account-level return. It is a daily independent basket diagnostic and does not model capital occupancy.
