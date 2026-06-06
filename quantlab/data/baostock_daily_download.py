"""Baostock daily OHLCV downloader.

This module writes daily raw CSVs into an isolated staging directory. It is the
data-package implementation behind the legacy ``scripts/download_baostock_ohlcv_range.py``
entrypoint.
"""

from __future__ import annotations

import argparse
import socket
import time
from pathlib import Path
from typing import Any

import pandas as pd


FIELDS = "date,open,high,low,close,volume,amount"
CSV_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume", "amount"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Baostock daily OHLCV CSVs into staging.")
    parser.add_argument("--data-dir", default="quantlab/01_data_daily/A_data")
    parser.add_argument("--market", default="all")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--staging-dir", required=True)
    parser.add_argument("--symbols-file", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--socket-timeout", type=float, default=45.0)
    parser.add_argument("--status-every", type=int, default=100)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-sleep", type=float, default=3.0)
    parser.add_argument("--relogin-every", type=int, default=200)
    return parser.parse_args()


def read_symbols(data_dir: Path, market: str) -> list[str]:
    path = data_dir / "instruments" / f"{market}.txt"
    symbols = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if parts:
            symbols.append(parts[0].upper())
    return sorted(set(symbols))


def read_symbols_file(path: Path) -> list[str]:
    symbols = []
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.strip().split(",")[0].strip()
        if token and not token.startswith("#"):
            symbols.append(token.upper())
    return sorted(set(symbols))


def qlib_to_baostock(symbol: str) -> str | None:
    symbol = symbol.upper()
    if symbol.startswith("SH"):
        return "sh." + symbol[2:]
    if symbol.startswith("SZ"):
        return "sz." + symbol[2:]
    return None


def normalize_rows(symbol: str, rows: list[list[Any]], fields: list[str] | None = None) -> pd.DataFrame:
    field_names = fields or FIELDS.split(",")
    df = pd.DataFrame(rows, columns=field_names)
    if df.empty:
        return pd.DataFrame(columns=CSV_COLUMNS)
    df.insert(0, "symbol", symbol)
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date"]).drop_duplicates("date").sort_values("date")
    return df[[c for c in CSV_COLUMNS if c in df.columns]]


def write_summary(staging_dir: Path, rows: list[dict[str, object]]) -> None:
    if rows:
        pd.DataFrame(rows).to_csv(staging_dir / "_download_summary.csv", index=False)


def login_baostock(bs: Any) -> None:
    login_result = bs.login()
    if login_result.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login_result.error_code} {login_result.error_msg}")


def download_one(symbol: str, args: argparse.Namespace, staging_dir: Path, bs: Any) -> dict[str, object]:
    code = qlib_to_baostock(symbol)
    out_path = staging_dir / f"{symbol}.csv"
    if code is None:
        return {"symbol": symbol, "code": "", "status": "bad_symbol", "rows": 0}
    if args.resume and out_path.exists() and out_path.stat().st_size > 0:
        try:
            old = pd.read_csv(out_path, usecols=["date"])
            return {"symbol": symbol, "code": code, "status": "skipped_existing", "rows": len(old)}
        except Exception:
            return {"symbol": symbol, "code": code, "status": "skipped_existing_unreadable", "rows": -1}

    rs = None
    last_status = None
    for attempt in range(args.retries + 1):
        if attempt:
            print(f"[retry] {symbol}: attempt {attempt + 1}/{args.retries + 1}", flush=True)
            try:
                bs.logout()
            except Exception:
                pass
            time.sleep(args.retry_sleep)
            login_baostock(bs)
        try:
            rs = bs.query_history_k_data_plus(
                code,
                FIELDS,
                start_date=args.start,
                end_date=args.end,
                frequency="d",
                adjustflag="2",
            )
        except Exception as exc:
            last_status = f"exception:{type(exc).__name__}"
            print(f"[warn] {symbol}: exception {type(exc).__name__}: {exc}", flush=True)
            continue
        if rs.error_code == "0":
            break
        last_status = f"error:{rs.error_code}"
        print(f"[warn] {symbol}: {rs.error_code} {rs.error_msg}", flush=True)
    if rs is None or rs.error_code != "0":
        return {"symbol": symbol, "code": code, "status": last_status or "error:unknown", "rows": 0}

    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return {"symbol": symbol, "code": code, "status": "empty", "rows": 0}

    df = normalize_rows(symbol, rows, FIELDS.split(","))
    df.to_csv(out_path, index=False)
    return {"symbol": symbol, "code": code, "status": "ok", "rows": len(df)}


def run_download(args: argparse.Namespace) -> pd.DataFrame:
    socket.setdefaulttimeout(args.socket_timeout)
    data_dir = Path(args.data_dir)
    staging_dir = Path(args.staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    symbols = read_symbols_file(Path(args.symbols_file)) if args.symbols_file else read_symbols(data_dir, args.market)
    if args.limit is not None:
        symbols = symbols[: args.limit]

    stats: list[dict[str, object]] = []
    pending_symbols: list[tuple[int, str]] = []
    total = len(symbols)
    for i, symbol in enumerate(symbols, 1):
        code = qlib_to_baostock(symbol)
        out_path = staging_dir / f"{symbol}.csv"
        if code is None:
            stats.append({"symbol": symbol, "code": "", "status": "bad_symbol", "rows": 0})
            continue
        if args.resume and out_path.exists() and out_path.stat().st_size > 0:
            try:
                old = pd.read_csv(out_path, usecols=["date"])
                stats.append({"symbol": symbol, "code": code, "status": "skipped_existing", "rows": len(old)})
            except Exception:
                stats.append({"symbol": symbol, "code": code, "status": "skipped_existing_unreadable", "rows": -1})
            if args.status_every > 0 and i % args.status_every == 0:
                write_summary(staging_dir, stats)
            continue
        pending_symbols.append((i, symbol))

    if not pending_symbols:
        write_summary(staging_dir, stats)
        return pd.DataFrame(stats)

    import baostock as bs

    login_baostock(bs)
    try:
        for i, symbol in pending_symbols:
            code = qlib_to_baostock(symbol)
            if i == 1 or i % args.status_every == 0 or i == total:
                print(f"[download] {i}/{total} {symbol} {code or ''}", flush=True)
            if args.relogin_every > 0 and i > 1 and (i - 1) % args.relogin_every == 0:
                print(f"[relogin] before {symbol}", flush=True)
                try:
                    bs.logout()
                except Exception:
                    pass
                login_baostock(bs)
            stats.append(download_one(symbol, args, staging_dir, bs))
            if args.status_every > 0 and i % args.status_every == 0:
                write_summary(staging_dir, stats)
            if args.sleep > 0:
                time.sleep(args.sleep)
    finally:
        bs.logout()
        write_summary(staging_dir, stats)

    return pd.DataFrame(stats)


def main() -> None:
    args = parse_args()
    stats_df = run_download(args)
    ok = int((stats_df["status"] == "ok").sum()) if not stats_df.empty else 0
    rows = int(stats_df["rows"].clip(lower=0).sum()) if not stats_df.empty else 0
    print(f"[done] staging={args.staging_dir} ok={ok} rows={rows}", flush=True)


if __name__ == "__main__":
    main()
