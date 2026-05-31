#!/usr/bin/env python3
"""Capital-aware account backtest from an EXP047-style selection_table.csv.

This fixes the misleading daily-basket metric by enforcing capital occupancy:
when one signal group is still open, later signal groups are skipped until the
planned exit time has passed.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="用 selection_table.csv 做资金占用账户级回测。")
    parser.add_argument("--selection-table", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument(
        "--reset-by-split",
        action="store_true",
        help="按 split 独立重置资金；用于和 historical_summary.csv 的 train/valid/test 口径对照。",
    )
    return parser.parse_args()


def max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    curve = pd.Series(values, dtype=float)
    return float((curve / curve.cummax() - 1.0).min())


def annualized_return(total_return: float, executed_groups: int) -> float | None:
    if executed_groups <= 0 or (1.0 + total_return) <= 0:
        return None
    years = executed_groups / 252.0
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


def load_selection(path: Path, top_n: int, start: str | None, end: str | None) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["rank"].astype(int) <= top_n].copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    df["entry_ts"] = pd.to_datetime(df["entry_time"], errors="coerce")
    df["exit_ts"] = pd.to_datetime(df["exit_time"], errors="coerce")
    df["net_ret_10bps"] = pd.to_numeric(df["net_ret_10bps"], errors="coerce")
    if start:
        df = df[df["trade_date"] >= start]
    if end:
        df = df[df["trade_date"] <= end]
    return df.sort_values(["entry_ts", "trade_date", "rank"]).reset_index(drop=True)


def run_one(df: pd.DataFrame, initial_capital: float, top_n: int, label: str) -> dict[str, Any]:
    capital = float(initial_capital)
    occupied_until: pd.Timestamp | None = None
    open_positions = ""
    trades: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = [{"event": "start", "date": "", "nav": capital, "label": label}]

    for trade_date, group in df.groupby("trade_date", sort=True):
        group = group.sort_values("rank").head(top_n)
        entry_ts = group["entry_ts"].iloc[0]
        exit_ts = group["exit_ts"].iloc[0]
        split = str(group["split"].iloc[0]) if "split" in group else label
        if pd.isna(entry_ts) or pd.isna(exit_ts) or not np.isfinite(group["net_ret_10bps"]).all():
            groups.append(
                {
                    "label": label,
                    "trade_date": trade_date,
                    "split": split,
                    "status": "pending_or_invalid",
                    "entry_time": entry_ts,
                    "exit_time": exit_ts,
                    "capital_before": capital,
                    "capital_after": capital,
                    "group_return": np.nan,
                    "tickers": ",".join(group["ticker"].astype(str).tolist()),
                    "skip_reason": "missing_entry_exit_or_return",
                    "open_positions": open_positions,
                }
            )
            continue
        if occupied_until is not None and entry_ts < occupied_until:
            groups.append(
                {
                    "label": label,
                    "trade_date": trade_date,
                    "split": split,
                    "status": "skipped",
                    "entry_time": entry_ts,
                    "exit_time": exit_ts,
                    "capital_before": capital,
                    "capital_after": capital,
                    "group_return": np.nan,
                    "tickers": ",".join(group["ticker"].astype(str).tolist()),
                    "skip_reason": "capital_occupied_by_open_positions",
                    "open_positions": open_positions,
                }
            )
            continue

        capital_before = capital
        weight = 1.0 / len(group)
        group_return = float((group["net_ret_10bps"] * weight).sum())
        group_pnl = capital_before * group_return
        capital = capital_before + group_pnl
        occupied_until = exit_ts
        open_positions = ",".join(group["ticker"].astype(str).tolist())
        groups.append(
            {
                "label": label,
                "trade_date": trade_date,
                "split": split,
                "status": "executed",
                "entry_time": entry_ts,
                "exit_time": exit_ts,
                "capital_before": capital_before,
                "capital_after": capital,
                "group_return": group_return,
                "group_pnl": group_pnl,
                "tickers": open_positions,
                "skip_reason": "",
                "open_positions": "",
            }
        )
        equity_rows.append({"event": "exit", "date": str(exit_ts), "nav": capital, "label": label})
        for _, row in group.iterrows():
            ret = float(row["net_ret_10bps"])
            trade_notional = capital_before * weight
            trades.append(
                {
                    "label": label,
                    "trade_date": trade_date,
                    "split": split,
                    "rank": int(row["rank"]),
                    "ticker": row["ticker"],
                    "model_score": float(row["model_score"]) if "model_score" in row and math.isfinite(float(row["model_score"])) else np.nan,
                    "entry_time": row["entry_time"],
                    "exit_time": row["exit_time"],
                    "net_ret_10bps": ret,
                    "notional": trade_notional,
                    "pnl": trade_notional * ret,
                }
            )

    group_df = pd.DataFrame(groups)
    equity = pd.DataFrame(equity_rows)
    executed = group_df[group_df["status"] == "executed"] if not group_df.empty else pd.DataFrame()
    skipped = group_df[group_df["status"] == "skipped"] if not group_df.empty else pd.DataFrame()
    returns = executed["group_return"].dropna() if not executed.empty else pd.Series(dtype=float)
    total_return = capital / initial_capital - 1.0
    summary = {
        "label": label,
        "initial_capital": initial_capital,
        "end_nav": capital,
        "total_return": total_return,
        "ann_ret_by_executed_groups": annualized_return(total_return, len(executed)),
        "max_drawdown_on_exit_nav": max_drawdown(equity["nav"].astype(float).tolist()),
        "signal_groups": int(group_df["trade_date"].nunique()) if not group_df.empty else 0,
        "executed_groups": int(len(executed)),
        "skipped_groups": int(len(skipped)),
        "completed_trades": int(len(trades)),
        "win_rate_by_group": float((returns > 0).mean()) if len(returns) else None,
        "mean_group_return": float(returns.mean()) if len(returns) else None,
    }
    return {"summary": summary, "groups": group_df, "trades": pd.DataFrame(trades), "equity": equity}


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = load_selection(Path(args.selection_table), args.top_n, args.start, args.end)
    if df.empty:
        raise ValueError("selection table has no rows after filtering")

    runs = []
    if args.reset_by_split and "split" in df.columns:
        for split, sub in df.groupby("split", sort=False):
            runs.append(run_one(sub.copy(), args.initial_capital, args.top_n, str(split)))
    else:
        runs.append(run_one(df, args.initial_capital, args.top_n, "continuous"))

    summaries = pd.DataFrame([run["summary"] for run in runs])
    groups = pd.concat([run["groups"] for run in runs], ignore_index=True)
    trades = pd.concat([run["trades"] for run in runs], ignore_index=True)
    equity = pd.concat([run["equity"] for run in runs], ignore_index=True)

    summaries.to_csv(out_dir / "account_summary.csv", index=False)
    groups.to_csv(out_dir / "account_signal_groups.csv", index=False)
    trades.to_csv(out_dir / "account_trades.csv", index=False)
    equity.to_csv(out_dir / "account_equity_curve.csv", index=False)

    payload = {
        "selection_table": args.selection_table,
        "top_n": args.top_n,
        "start": args.start,
        "end": args.end,
        "reset_by_split": args.reset_by_split,
        "summaries": summaries.to_dict(orient="records"),
        "notes": [
            "This is the corrected capital-aware account metric.",
            "daily_basket_returns.csv is a signal-quality diagnostic and should not be used as account return.",
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Capital-aware selection table backtest",
        "",
        f"- selection_table: `{args.selection_table}`",
        f"- top_n: `{args.top_n}`",
        f"- reset_by_split: `{args.reset_by_split}`",
        "",
        "## Summary",
        "",
        summaries.to_markdown(index=False, floatfmt=".6f"),
        "",
        "## Outputs",
        "",
        "- `account_signal_groups.csv`: 每个信号组执行或跳过情况。",
        "- `account_trades.csv`: 逐笔交易收益。",
        "- `account_equity_curve.csv`: 只在退出时更新的账户净值曲线。",
        "- `account_summary.csv`: 修正后的账户级收益摘要。",
    ]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] {out_dir}")
    print(summaries.to_string(index=False))


if __name__ == "__main__":
    main()
