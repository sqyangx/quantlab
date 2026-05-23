# QuantLab

English | [中文](README_CN.md)

A quantitative trading system for China A-share markets, fusing three Microsoft open-source projects into a unified T+1 daily trading pipeline.

> Current architecture map: [HTML preview](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/project_architecture.html) ([source](docs/project_architecture.html))

| Component | Role |
|-----------|------|
| [Qlib](https://github.com/microsoft/qlib) | Data infrastructure, Alpha158 factor engine, backtesting framework |
| [Kronos](https://github.com/microsoft/Chronos-Forecasting) | Foundation Transformer model for K-line sequence forecasting |
| [RD-Agent](https://github.com/microsoft/RD-Agent) | LLM-driven evolutionary R&D agent for automated factor/model discovery |

## Recent Additions

- **Agentic review layer**: `quantlab.agentic` adds a reusable post-selection review module for liquidity checks, sector-flow exposure, industry concentration, veto/reduce/approve decisions, and daily review exports.
- **Sector fund-flow data layer**: `quantlab.data.sector_flow_*` downloads, normalizes, aligns, and featurizes sector fund-flow data so it can be joined with the existing Qlib daily calendar and industry map.
- **Feature article**: [Agentic feature article](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/agentic_feature_article.html) explains the new review layer, sector-flow alignment, daily decision flow, and experiment path.
- **Project architecture HTML**: [HTML preview](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/project_architecture.html) provides a visual map of data, signals, selector fusion, agentic review, execution, risk, evaluation, and operations. The source file is [docs/project_architecture.html](docs/project_architecture.html).

## Architecture

For the latest full-system view, open the [rendered HTML preview](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/project_architecture.html). GitHub's normal `blob` page shows the HTML source code by design.

<img width="1024" height="1536" alt="ChatGPT Image 2026年4月18日 20_45_33" src="https://github.com/user-attachments/assets/e15b27b8-69a3-4df0-ac72-9df71e04c311" />

**Key design principle:** All data queries enforce `anchor_date` — no module may access data beyond date T, preventing forward-looking bias.

## Modules

| Module | Path | Description |
|--------|------|-------------|
| M1 Data | `data/data_manager.py` | Data update (Yahoo/Baostock/CSV -> Qlib bin) + time-isolated access |
| M1.5 Viewer | `data/data_viewer.py` | CSV export, K-line charts (Plotly), portfolio overview |
| M2 Alpha | `signal/signal_alpha.py` | Alpha158 + LightGBM (daily trend/momentum signal) |
| M3 Kronos | `signal/signal_kronos.py` | Kronos 5-day forecast (K-line pattern signal) |
| M4 RD-Agent | `signal/signal_rdagent.py`, `signal/factor_spec.py` | RD-Agent evolved factors and deterministic factor-spec compilation |
| M5 Ensemble | `signal/signal_ensemble.py` | Signal fusion (rank normalization, expanding IC weighting) |
| M6 Execution | `execution/execution.py` | T+1 open-price trade execution |
| M7 Risk | `risk_control/risk_control.py` | Single-stock stoploss, industry cap, portfolio circuit breaker |
| M8 Evaluation | `evaluation/evaluation.py` | Performance metrics (Sharpe, IC decay, attribution) |
| M9 Runner | `main.py` | Daily backtest scheduler with checkpoint/resume |
| Agentic Review | `agentic/` | Independent review layer for candidate ranking, risk findings, veto/reduce decisions, and review artifacts |
| Sector Flow | `data/sector_flow_*.py` | Sector fund-flow download, normalization, calendar alignment, and rolling features |

## Quick Start

### Prerequisites

- Python 3.10 or 3.11 (recommended)
- C++ compiler (qlib has Cython extensions)
  - **Windows:** Install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/), select "C++ build tools"
  - **Linux:** `sudo apt install build-essential`
  - **macOS:** `xcode-select --install`

### Installation

```bash
# Clone the repo (with submodules)
git clone --recursive https://github.com/sqyangx/quantlab.git
cd quantlab

# Create conda environment
conda create -n quantlab python=3.11 -y
conda activate quantlab

# Install qlib (local source, triggers Cython compilation)
pip install -e ./qlib

# Install quantlab
pip install -e .

# Verify environment + download A-share data (~200-500MB)
python quantlab/setup_and_verify.py
```

### Run Backtest

```bash
# Full backtest
python quantlab/main.py --config quantlab/configs/backtest.yaml

# Resume from checkpoint
python quantlab/main.py --resume checkpoints/checkpoint_2024-06-28.pkl
```

### Run Tests

```bash
python -m pytest quantlab/tests/ -v
```

## Configuration

Main config: `quantlab/configs/backtest.yaml`

```yaml
# Backtest period
start_date: "2023-01-01"
end_date: "2025-03-01"

# Market
market: "csi300"
initial_cash: 1000000

# Pipeline switches
enable_alpha: true
enable_kronos: true
enable_rdagent: false          # Requires LLM API, disabled by default

# Execution
max_positions: 10
max_single_weight: 0.20

# Risk control
stop_loss_pct: 0.08            # 8% individual stoploss
max_industry_pct: 0.30         # 30% single industry cap
circuit_breaker_pct: 0.10      # 10% portfolio circuit breaker
```

See [backtest.yaml](quantlab/configs/backtest.yaml) for all parameters.

## How It Works

### T+1 Trading Cycle

1. **Day T close** — Fetch all data up to day T
2. **Signal generation** — Three pipelines produce independent signals:
   - **Alpha158**: 158 technical factors + LightGBM, retrained every 20 trading days
   - **Kronos**: Transformer forecasts next 5-day OHLCV, 10-sample ensemble for uncertainty
   - **RD-Agent**: LLM-evolved factors, weekly evolution loop (optional)
3. **Signal fusion** — Rank normalize each signal, weight by expanding IC correlation
4. **Order generation** — Select top/bottom stocks with position limits
5. **Day T+1 open** — Execute orders at open price (buy only if open <= target price)
6. **Risk check** — Stoploss / industry cap / circuit breaker applied continuously

### Risk Control (3 Levels)

| Level | Trigger | Action |
|-------|---------|--------|
| Single-stock | Drawdown >= 8% from high | Force sell |
| Industry | Exposure > 30% of portfolio | Reduce position |
| Portfolio | Drawdown >= 10% from high-water mark | Pause trading 5 days |

## Project Structure

```
quantlab/
├── configs/                    # YAML configurations
│   ├── backtest.yaml           # Main backtest config
│   ├── kronos_recipes.yaml     # Kronos model recipes
│   └── rdagent_evolution.yaml  # RD-Agent evolution settings
├── agentic/                    # Agentic candidate review layer
├── data/                       # M1 & M1.5: Data layer
├── signal/                     # M2-M5: Signal pipelines
├── execution/                  # M6: Trade execution
├── risk_control/               # M7: Risk management
├── evaluation/                 # M8: Performance analysis
├── tests/                      # Test suite
├── main.py                     # M9: Backtest runner
└── setup_and_verify.py         # Environment setup
```

## Documentation

- [Agentic feature article](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/agentic_feature_article.html) - Detailed introduction to the agentic review layer and sector-flow feature design ([source](docs/agentic_feature_article.html))
- [Rendered architecture map](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/project_architecture.html) - Current architecture map and new agentic/sector-flow design ([source](docs/project_architecture.html))
- [Factor-Spec Pipeline](docs/factor_spec_pipeline.md) - Structured factor specification, deterministic compilation, and sampled smoke testing for RD-Agent-style factor search
- [DESIGN.md](DESIGN.md) — Architecture overview (Chinese)
- [DETAIL_DESIGN.md](DETAIL_DESIGN.md) — Detailed module specifications M1-M9 (Chinese)
- [docs/](docs/) — Per-module usage guides (Chinese)

## Acknowledgements

This project builds on three excellent open-source projects from Microsoft:

- [Qlib](https://github.com/microsoft/qlib) — AI-oriented quantitative investment platform
- [Kronos](https://github.com/microsoft/Chronos-Forecasting) — Pretrained time series forecasting models
- [RD-Agent](https://github.com/microsoft/RD-Agent) — LLM-based research and development agent

## License

[MIT](LICENSE)
