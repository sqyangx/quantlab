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
    parser.add_argument(
        "--candidate-n",
        type=int,
        default=None,
        help="候选池最大 rank；用于涨停递补。默认读取 selection-table 中全部 rank。",
    )
    parser.add_argument("--initial-capital", type=float, default=100_000.0)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--data-dir", default="quantlab/02_data_5min/min_data", help="5min qlib 数据目录，用于判断入场开盘涨停。")
    parser.add_argument(
        "--stock-basic",
        default="quantlab/08_archive_tmp/stock_basic/baostock_stock_basic_latest.csv",
        help="Baostock 股票基础信息缓存，用于通过证券简称识别 ST/*ST。",
    )
    parser.add_argument(
        "--limit-up-mode",
        choices=["none", "drop_signal_limit_up", "replace_unbuyable", "skip_unbuyable"],
        default="none",
        help=(
            "none=旧口径；drop_signal_limit_up=信号日15:00已涨停则不推荐，并从后续候选递补到top_n；"
            "replace_unbuyable=保留top5排序，入场涨停则用后续候选递补到top_n；"
            "skip_unbuyable=保留top5排序，入场涨停则不买且不递补。"
        ),
    )
    parser.add_argument("--limit-up-buffer", type=float, default=0.002, help="涨停判断缓冲；10%%板按 9.8%% 以上视为涨停。")
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


def load_selection(path: Path, candidate_n: int | None, start: str | None, end: str | None) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["rank"] = df["rank"].astype(int)
    if candidate_n is not None:
        df = df[df["rank"] <= candidate_n].copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    df["entry_ts"] = pd.to_datetime(df["entry_time"], errors="coerce")
    df["exit_ts"] = pd.to_datetime(df["exit_time"], errors="coerce")
    df["net_ret_10bps"] = pd.to_numeric(df["net_ret_10bps"], errors="coerce")
    if start:
        df = df[df["trade_date"] >= start]
    if end:
        df = df[df["trade_date"] <= end]
    return df.sort_values(["entry_ts", "trade_date", "rank"]).reset_index(drop=True)


def read_calendar(path: Path) -> pd.DatetimeIndex:
    rows = pd.read_csv(path, header=None).iloc[:, 0]
    return pd.DatetimeIndex(pd.to_datetime(rows, errors="coerce").dropna())


def read_field_bin(path: Path, calendar_len: int) -> np.ndarray:
    raw = np.fromfile(path, dtype="<f4")
    out = np.full(calendar_len, np.nan, dtype=np.float32)
    if raw.size <= 1:
        return out
    start_idx = int(raw[0])
    values = raw[1:]
    end_idx = min(calendar_len, start_idx + len(values))
    if 0 <= start_idx < end_idx:
        out[start_idx:end_idx] = values[: end_idx - start_idx]
    return out


class PriceStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.calendar = read_calendar(data_dir / "calendars" / "5min.txt")
        self.calendar_pos = {ts: i for i, ts in enumerate(self.calendar)}
        self.trading_dates = sorted({ts.date() for ts in self.calendar})
        self.date_to_pos = {d: i for i, d in enumerate(self.trading_dates)}
        self.cache: dict[tuple[str, str], np.ndarray] = {}

    def field_at(self, ticker: str, ts: pd.Timestamp, field: str) -> float:
        key = (ticker.upper(), field)
        if key not in self.cache:
            path = self.data_dir / "features" / ticker.lower() / f"{field}.5min.bin"
            self.cache[key] = read_field_bin(path, len(self.calendar)) if path.exists() else np.full(
                len(self.calendar), np.nan, dtype=np.float32
            )
        pos = self.calendar_pos.get(ts)
        if pos is None:
            return float("nan")
        return float(self.cache[key][pos])

    def previous_trading_day(self, date_value: Any) -> Any | None:
        pos = self.date_to_pos.get(pd.Timestamp(date_value).date())
        if pos is None or pos <= 0:
            return None
        return self.trading_dates[pos - 1]


def load_stock_basic(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        if "code" not in df.columns:
            return {}
        df["ticker"] = df["code"].astype(str).str.replace("sh.", "SH", regex=False).str.replace("sz.", "SZ", regex=False)
    if "code_name" not in df.columns:
        df["code_name"] = ""
    if "is_st" not in df.columns:
        df["is_st"] = df["code_name"].astype(str).str.upper().str.contains("ST", regex=False)
    out = {}
    for row in df.itertuples(index=False):
        ticker = str(getattr(row, "ticker")).upper()
        out[ticker] = {"code_name": str(getattr(row, "code_name", "")), "is_st": bool(getattr(row, "is_st", False))}
    return out


def limit_up_threshold(ticker: str, buffer: float, is_st: bool = False) -> float:
    if is_st:
        return 0.05 - buffer
    code = ticker.upper()[2:]
    base = 0.20 if code.startswith(("300", "301", "302", "688")) else 0.10
    return base - buffer


def mark_entry_limit_up(
    df: pd.DataFrame, price_store: PriceStore, buffer: float, stock_basic: dict[str, dict[str, Any]] | None = None
) -> pd.DataFrame:
    out = df.copy()
    stock_basic = stock_basic or {}
    code_names: list[str] = []
    st_flags: list[bool] = []
    prev_close_values: list[float] = []
    signal_prev_close_values: list[float] = []
    signal_close_values: list[float] = []
    signal_close_returns: list[float] = []
    signal_limit_flags: list[bool] = []
    entry_open_values: list[float] = []
    entry_open_returns: list[float] = []
    entry_limit_flags: list[bool] = []
    reasons: list[str] = []
    for row in out.itertuples(index=False):
        entry_ts = getattr(row, "entry_ts")
        ticker = str(getattr(row, "ticker")).upper()
        info = stock_basic.get(ticker, {})
        code_name = str(info.get("code_name", ""))
        is_st = bool(info.get("is_st", False))
        trade_date = getattr(row, "trade_date")
        prev_signal_day = price_store.previous_trading_day(trade_date)
        signal_prev_close_ts = pd.Timestamp(f"{prev_signal_day} 15:00:00") if prev_signal_day is not None else pd.NaT
        signal_close_ts = pd.Timestamp(trade_date + " 15:00:00")
        signal_prev_close = (
            price_store.field_at(ticker, signal_prev_close_ts, "close") if pd.notna(signal_prev_close_ts) else float("nan")
        )
        signal_close = price_store.field_at(ticker, signal_close_ts, "close")
        if np.isfinite(signal_prev_close) and signal_prev_close > 0 and np.isfinite(signal_close) and signal_close > 0:
            signal_ret = signal_close / signal_prev_close - 1.0
            signal_is_limit = signal_ret >= limit_up_threshold(ticker, buffer, is_st)
        else:
            signal_ret = float("nan")
            signal_is_limit = False
        prev_close_ts = pd.Timestamp(getattr(row, "trade_date") + " 15:00:00")
        prev_close = price_store.field_at(ticker, prev_close_ts, "close") if pd.notna(entry_ts) else float("nan")
        entry_open = price_store.field_at(ticker, entry_ts, "open") if pd.notna(entry_ts) else float("nan")
        if np.isfinite(prev_close) and prev_close > 0 and np.isfinite(entry_open) and entry_open > 0:
            ret = entry_open / prev_close - 1.0
            is_limit = ret >= limit_up_threshold(ticker, buffer, is_st)
            reason = "entry_open_limit_up" if is_limit else ""
        else:
            ret = float("nan")
            is_limit = False
            reason = "missing_limit_check_price"
        code_names.append(code_name)
        st_flags.append(is_st)
        signal_prev_close_values.append(float(signal_prev_close))
        signal_close_values.append(float(signal_close))
        signal_close_returns.append(float(signal_ret))
        signal_limit_flags.append(bool(signal_is_limit))
        prev_close_values.append(float(prev_close))
        entry_open_values.append(float(entry_open))
        entry_open_returns.append(float(ret))
        entry_limit_flags.append(bool(is_limit))
        reasons.append(reason)
    out["code_name"] = code_names
    out["is_st"] = st_flags
    out["signal_prev_close"] = signal_prev_close_values
    out["signal_close"] = signal_close_values
    out["signal_close_ret"] = signal_close_returns
    out["signal_close_limit_up"] = signal_limit_flags
    out["prev_signal_close"] = prev_close_values
    out["entry_open"] = entry_open_values
    out["entry_open_ret"] = entry_open_returns
    out["entry_open_limit_up"] = entry_limit_flags
    out["limit_up_reason"] = reasons
    return out


def select_group(group: pd.DataFrame, top_n: int, mode: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    group = group.sort_values("rank")
    if mode == "none":
        selected = group.head(top_n).copy()
        rejected = group.iloc[0:0].copy()
        return selected, rejected
    if mode == "skip_unbuyable":
        initial = group.head(top_n).copy()
        selected = initial[~initial["entry_open_limit_up"]].copy()
        rejected = initial[initial["entry_open_limit_up"]].copy()
        return selected, rejected
    if mode == "drop_signal_limit_up":
        selected = group[~group["signal_close_limit_up"]].head(top_n).copy()
        rejected = group[group["signal_close_limit_up"]].copy()
        return selected, rejected
    if mode == "replace_unbuyable":
        selected = group[~group["entry_open_limit_up"]].head(top_n).copy()
        initial = group.head(top_n)
        rejected = initial[initial["entry_open_limit_up"]].copy()
        return selected, rejected
    raise ValueError(f"unsupported limit-up mode: {mode}")


def run_one(df: pd.DataFrame, initial_capital: float, top_n: int, label: str, limit_up_mode: str) -> dict[str, Any]:
    capital = float(initial_capital)
    occupied_until: pd.Timestamp | None = None
    open_positions = ""
    trades: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = [{"event": "start", "date": "", "nav": capital, "label": label}]

    for trade_date, group in df.groupby("trade_date", sort=True):
        raw_group = group.sort_values("rank")
        group, rejected = select_group(raw_group, top_n, limit_up_mode)
        split = str(raw_group["split"].iloc[0]) if "split" in raw_group else label
        rejected_tickers = ",".join(rejected["ticker"].astype(str).tolist()) if not rejected.empty else ""
        if group.empty:
            groups.append(
                {
                    "label": label,
                    "trade_date": trade_date,
                    "split": split,
                    "status": "skipped",
                    "entry_time": "",
                    "exit_time": "",
                    "capital_before": capital,
                    "capital_after": capital,
                    "group_return": np.nan,
                    "tickers": "",
                    "selected_count": 0,
                    "rejected_limit_up_count": int(len(rejected)),
                    "rejected_limit_up_tickers": rejected_tickers,
                    "skip_reason": "all_selected_unbuyable_at_entry_open",
                    "open_positions": open_positions,
                }
            )
            continue
        entry_ts = group["entry_ts"].iloc[0]
        exit_ts = group["exit_ts"].iloc[0]
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
                    "selected_count": int(len(group)),
                    "rejected_limit_up_count": int(len(rejected)),
                    "rejected_limit_up_tickers": rejected_tickers,
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
                    "selected_count": int(len(group)),
                    "rejected_limit_up_count": int(len(rejected)),
                    "rejected_limit_up_tickers": rejected_tickers,
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
                "selected_count": int(len(group)),
                "rejected_limit_up_count": int(len(rejected)),
                "rejected_limit_up_tickers": rejected_tickers,
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
                    "code_name": row.get("code_name", ""),
                    "is_st": bool(row.get("is_st", False)),
                    "model_score": float(row["model_score"]) if "model_score" in row and math.isfinite(float(row["model_score"])) else np.nan,
                    "entry_time": row["entry_time"],
                    "exit_time": row["exit_time"],
                    "net_ret_10bps": ret,
                    "entry_open_limit_up": bool(row.get("entry_open_limit_up", False)) if hasattr(row, "get") else bool(row["entry_open_limit_up"]),
                    "entry_open_ret": float(row.get("entry_open_ret", np.nan)) if hasattr(row, "get") else float(row["entry_open_ret"]),
                    "prev_signal_close": float(row.get("prev_signal_close", np.nan)) if hasattr(row, "get") else float(row["prev_signal_close"]),
                    "entry_open": float(row.get("entry_open", np.nan)) if hasattr(row, "get") else float(row["entry_open"]),
                    "notional": trade_notional,
                    "pnl": trade_notional * ret,
                    "source_npz": row.get("source_npz", ""),
                    "model_path": row.get("model_path", ""),
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
        "limit_up_mode": limit_up_mode,
        "rejected_limit_up_rows": int(group_df["rejected_limit_up_count"].fillna(0).sum()) if "rejected_limit_up_count" in group_df else 0,
    }
    return {"summary": summary, "groups": group_df, "trades": pd.DataFrame(trades), "equity": equity}


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = load_selection(Path(args.selection_table), args.candidate_n, args.start, args.end)
    if df.empty:
        raise ValueError("selection table has no rows after filtering")
    price_store = PriceStore(Path(args.data_dir))
    stock_basic = load_stock_basic(Path(args.stock_basic))
    df = mark_entry_limit_up(df, price_store, args.limit_up_buffer, stock_basic)

    runs = []
    if args.reset_by_split and "split" in df.columns:
        for split, sub in df.groupby("split", sort=False):
            runs.append(run_one(sub.copy(), args.initial_capital, args.top_n, str(split), args.limit_up_mode))
    else:
        runs.append(run_one(df, args.initial_capital, args.top_n, "continuous", args.limit_up_mode))

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
        "candidate_n": args.candidate_n,
        "data_dir": args.data_dir,
        "stock_basic": args.stock_basic,
        "limit_up_mode": args.limit_up_mode,
        "limit_up_buffer": args.limit_up_buffer,
        "start": args.start,
        "end": args.end,
        "reset_by_split": args.reset_by_split,
        "summaries": summaries.to_dict(orient="records"),
        "notes": [
            "This is the corrected capital-aware account metric.",
            "daily_basket_returns.csv is a signal-quality diagnostic and should not be used as account return.",
            "Limit-up handling uses entry-day 09:35 open vs signal-day 15:00 close for buyability.",
            "drop_signal_limit_up uses signal-day 15:00 close vs previous trading-day 15:00 close as an ex-ante recommendation filter.",
            "ST/*ST names from stock_basic use 5% limit-up threshold; other main-board names use 10%, ChiNext/STAR use 20%.",
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Capital-aware selection table backtest",
        "",
        f"- selection_table: `{args.selection_table}`",
        f"- top_n: `{args.top_n}`",
        f"- candidate_n: `{args.candidate_n}`",
        f"- data_dir: `{args.data_dir}`",
        f"- stock_basic: `{args.stock_basic}`",
        f"- limit_up_mode: `{args.limit_up_mode}`",
        f"- limit_up_buffer: `{args.limit_up_buffer}`",
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
