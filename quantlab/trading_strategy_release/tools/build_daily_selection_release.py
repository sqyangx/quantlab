#!/usr/bin/env python3
"""Build daily publishable selection files from account-level backtest outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成每日交易发布结果。")
    parser.add_argument("--account-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def clean_record(row: pd.Series) -> dict:
    out = {}
    for key, value in row.to_dict().items():
        if key in {"source_npz", "model_path"}:
            continue
        if pd.isna(value):
            out[key] = None
        else:
            out[key] = value
    return out


def main() -> None:
    args = parse_args()
    account_dir = Path(args.account_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.json", "*.md", "*.csv"):
        for path in out_dir.glob(pattern):
            path.unlink()

    groups = pd.read_csv(account_dir / "account_signal_groups.csv")
    trades = pd.read_csv(account_dir / "account_trades.csv")
    trades = trades.drop(columns=[c for c in ("source_npz", "model_path") if c in trades.columns])
    summary = pd.read_csv(account_dir / "account_summary.csv")
    groups["trade_date"] = groups["trade_date"].astype(str)
    trades["trade_date"] = trades["trade_date"].astype(str)

    daily_rows = []
    for date, group in groups.groupby("trade_date", sort=True):
        group_row = group.iloc[0]
        trade_rows = trades[trades["trade_date"] == date].sort_values("rank")
        status = str(group_row["status"])
        tickers = [x for x in str(group_row.get("tickers", "")).split(",") if x]
        payload = {
            "trade_date": date,
            "status": status,
            "entry_time": group_row.get("entry_time"),
            "exit_time": group_row.get("exit_time"),
            "capital_before": group_row.get("capital_before"),
            "capital_after": group_row.get("capital_after"),
            "group_return": group_row.get("group_return"),
            "group_pnl": group_row.get("group_pnl"),
            "tickers": tickers,
            "skip_reason": group_row.get("skip_reason") if status != "executed" else "",
            "open_positions": group_row.get("open_positions") if status != "executed" else "",
            "trades": [clean_record(row) for _, row in trade_rows.iterrows()],
        }
        (out_dir / f"{date}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        lines = [
            f"# {date} Model-A Top5 Selection",
            "",
            f"- status: `{status}`",
            f"- entry_time: `{group_row.get('entry_time')}`",
            f"- exit_time: `{group_row.get('exit_time')}`",
            f"- capital_before: `{float(group_row.get('capital_before')):.6f}`",
            f"- capital_after: `{float(group_row.get('capital_after')):.6f}`",
        ]
        if status == "executed":
            lines.extend(
                [
                    f"- group_return: `{float(group_row.get('group_return')):.6f}`",
                    f"- group_pnl: `{float(group_row.get('group_pnl')):.6f}`",
                    "",
                    "## Trades",
                    "",
                    trade_rows.to_markdown(index=False, floatfmt=".6f"),
                ]
            )
        else:
            lines.extend(
                [
                    f"- skip_reason: `{group_row.get('skip_reason')}`",
                    f"- open_positions: `{group_row.get('open_positions')}`",
                    "",
                    "## Planned Tickers",
                    "",
                    ", ".join(tickers),
                ]
            )
        (out_dir / f"{date}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

        daily_rows.append(
            {
                "trade_date": date,
                "status": status,
                "entry_time": group_row.get("entry_time"),
                "exit_time": group_row.get("exit_time"),
                "capital_before": group_row.get("capital_before"),
                "capital_after": group_row.get("capital_after"),
                "group_return": group_row.get("group_return"),
                "group_pnl": group_row.get("group_pnl"),
                "tickers": ",".join(tickers),
                "skip_reason": group_row.get("skip_reason") if status != "executed" else "",
                "open_positions": group_row.get("open_positions") if status != "executed" else "",
            }
        )

    pd.DataFrame(daily_rows).to_csv(out_dir / "daily_selection_summary.csv", index=False)
    summary.to_csv(out_dir / "account_summary.csv", index=False)
    index = {
        "source_account_dir": str(account_dir),
        "daily_count": len(daily_rows),
        "executed_count": int((pd.DataFrame(daily_rows)["status"] == "executed").sum()),
        "skipped_count": int((pd.DataFrame(daily_rows)["status"] == "skipped").sum()),
        "account_summary": summary.to_dict(orient="records"),
    }
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = [
        "# Daily Trading Release Results",
        "",
        "These files are generated from the corrected capital-aware Model-A account backtest.",
        "",
        "- `daily_selection_summary.csv`: one row per signal day.",
        "- `{YYYY-MM-DD}.json`: structured daily result.",
        "- `{YYYY-MM-DD}.md`: readable daily release note.",
        "- `account_summary.csv`: corrected account-level summary.",
        "",
        "Model weights and experiment directories are intentionally excluded from this release folder.",
    ]
    (out_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(f"[done] {out_dir}")


if __name__ == "__main__":
    main()
