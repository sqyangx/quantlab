# GitHub Release Checklist

Remote checked:

```text
https://github.com/sqyangx/quantlab
```

The current remote repository does not contain:

- `quantlab/post_analysis/tradingagents`
- corrected account backtest tooling
- SmartStock AI static UI
daily Model-A trading release result files as a public GitHub artifact

## Files To Publish

Recommended publish root:

```text
quantlab/trading_strategy_release/
```

Publish these folders:

- `frontend/tradingagents_modela_ui_20260501_20260529/`
- `src/quantlab/post_analysis/tradingagents/`
- `tools/`
- `README.md`
- `GITHUB_RELEASE_CHECKLIST.md`
- `.gitignore`

## Do Not Publish

- `quantlab/model_registry/`
- `quantlab/trading_strategy_release/data/daily_results_2026/`
- `quantlab/08_archive_tmp/`
- `quantlab/07_stock_selection_strategies/`
- `quantlab/04_kronos_5min/`
- `quantlab/02_data_5min/`
- `quantlab/01_data_daily/`
- `quantlab/experiments/`
- any `*.pt`, `*.pth`, `*.ckpt`, `*.npz`, `*.bin`, `*.pkl`

## Verification

Release folder scan result:

- no model/checkpoint files found
- no `01_*` to `08_*` artifact directories found
- no `experiments` directory found

## Notes

The Model-A checkpoint is referenced only by metadata in documentation. The checkpoint itself must remain local and must not be committed.
