# 5min Model-A Portfolio Backtest

- initial_capital: `100,000.00`
- top_n: `5`
- limit_up_mode: `skip_unbuyable`
- limit_up_buffer: `0.002`
- entry: `next trading day 09:35 open`
- exit: `entry day + 1 trading day 15:00:00`
- roundtrip_cost_bps: `10.0`
- completed_trades: `6`
- skipped_entries: `6`
- total_return: `0.050510`
- max_drawdown: `-0.012447`

## Outputs

- `selection_records.csv`: 每日 Model-A topN 信号。
- `trades.csv`: 实际成交并完成退出的持仓。
- `skipped_entries.csv`: 因资金占用等原因未买入的信号。
- `equity_curve.csv`: 账户级资金曲线。
