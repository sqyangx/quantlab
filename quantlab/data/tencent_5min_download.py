"""Tencent Finance 5-minute OHLCV downloader.

The downloader writes raw per-symbol CSVs into an isolated staging directory.
It does not update canonical Qlib providers directly; update workflows should
validate the staging output before promoting it into ``quantlab/02_data_5min``.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd


API_URL = "http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={code},m5,,{count}"
USER_AGENT = "Mozilla/5.0"
CSV_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume", "amount", "adjustflag"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Tencent Finance 5-minute OHLCV CSVs.")
    parser.add_argument("--data-dir", default="quantlab/01_data_daily/A_data", help="Qlib provider used only for instruments.")
    parser.add_argument("--market", default="all", help="Instrument file under instruments/<market>.txt.")
    parser.add_argument("--start", required=True, help="Download start date, e.g. 2026-06-02.")
    parser.add_argument("--end", required=True, help="Download end date, e.g. 2026-06-02.")
    parser.add_argument("--staging-dir", required=True, help="Output directory for raw per-symbol CSV files.")
    parser.add_argument("--symbols-file", default=None, help="Optional file with one qlib symbol per line.")
    parser.add_argument("--resume", action="store_true", help="Skip existing non-empty symbol CSVs.")
    parser.add_argument("--limit", type=int, default=None, help="Limit symbols for smoke tests.")
    parser.add_argument("--recent-bars", type=int, default=640, help="Tencent recent m5 bars to request.")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument("--workers", type=int, default=1, help="Concurrent request workers. Use 1 for sequential downloads.")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-sleep", type=float, default=2.0)
    parser.add_argument("--status-every", type=int, default=25)
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


def qlib_to_tencent(symbol: str) -> str | None:
    symbol = symbol.upper()
    if symbol.startswith("SH"):
        return "sh" + symbol[2:]
    if symbol.startswith("SZ"):
        return "sz" + symbol[2:]
    return None


def fetch_json(code: str, recent_bars: int, timeout: float) -> dict[str, Any]:
    url = API_URL.format(code=code, count=recent_bars)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="replace")
    return json.loads(raw)


def normalize_rows(symbol: str, rows: list[Any], start: str, end: str) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    for row in rows:
        if len(row) < 6:
            continue
        ts = pd.to_datetime(str(row[0]), format="%Y%m%d%H%M", errors="coerce")
        if pd.isna(ts) or ts < start_ts or ts > end_ts:
            continue
        try:
            open_px = float(row[1])
            close_px = float(row[2])
            high_px = float(row[3])
            low_px = float(row[4])
            volume_hands = float(row[5])
        except (TypeError, ValueError):
            continue
        volume_shares = volume_hands * 100.0
        records.append(
            {
                "date": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "open": open_px,
                "high": high_px,
                "low": low_px,
                "close": close_px,
                "volume": volume_shares,
                "amount": close_px * volume_shares,
                "adjustflag": 3,
            }
        )
    if not records:
        return pd.DataFrame(columns=CSV_COLUMNS)
    return pd.DataFrame(records).drop_duplicates("date").sort_values("date")[CSV_COLUMNS]


def write_summary(staging_dir: Path, rows: list[dict[str, object]]) -> None:
    if rows:
        pd.DataFrame(rows).to_csv(staging_dir / "_download_summary.csv", index=False)


def download_one(symbol: str, args: argparse.Namespace, staging_dir: Path) -> dict[str, object]:
    code = qlib_to_tencent(symbol)
    out_path = staging_dir / f"{symbol}.csv"
    if code is None:
        return {"symbol": symbol, "code": "", "status": "bad_symbol", "rows": 0}
    if args.resume and out_path.exists() and out_path.stat().st_size > 0:
        old = pd.read_csv(out_path, usecols=["date"])
        return {"symbol": symbol, "code": code, "status": "skipped_existing", "rows": len(old)}

    last_error = ""
    payload = None
    for attempt in range(args.retries + 1):
        try:
            payload = fetch_json(code, args.recent_bars, args.timeout)
            break
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}:{exc}"
            if attempt < args.retries:
                time.sleep(args.retry_sleep)
    if payload is None:
        return {"symbol": symbol, "code": code, "status": f"error:{last_error}", "rows": 0}

    item = payload.get("data", {}).get(code, {})
    bars = item.get("m5") or []
    df = normalize_rows(symbol, bars, args.start, args.end)
    if df.empty:
        return {"symbol": symbol, "code": code, "status": "empty", "rows": 0}
    df.to_csv(out_path, index=False)
    return {"symbol": symbol, "code": code, "status": "ok", "rows": len(df)}


def run_download(args: argparse.Namespace) -> pd.DataFrame:
    data_dir = Path(args.data_dir)
    staging_dir = Path(args.staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    symbols = read_symbols_file(Path(args.symbols_file)) if args.symbols_file else read_symbols(data_dir, args.market)
    if args.limit is not None:
        symbols = symbols[: args.limit]

    stats: list[dict[str, object]] = []
    if args.workers <= 1:
        for i, symbol in enumerate(symbols, 1):
            print(f"[download] {i}/{len(symbols)} {symbol} {qlib_to_tencent(symbol) or ''}", flush=True)
            stats.append(download_one(symbol, args, staging_dir))
            if args.status_every > 0 and i % args.status_every == 0:
                write_summary(staging_dir, stats)
            if args.sleep > 0:
                time.sleep(args.sleep)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(download_one, symbol, args, staging_dir): symbol for symbol in symbols}
            for i, future in enumerate(as_completed(futures), 1):
                symbol = futures[future]
                try:
                    row = future.result()
                except Exception as exc:
                    row = {
                        "symbol": symbol,
                        "code": qlib_to_tencent(symbol) or "",
                        "status": f"exception:{type(exc).__name__}:{exc}",
                        "rows": 0,
                    }
                stats.append(row)
                if i % max(args.status_every, 1) == 0 or i == len(symbols):
                    ok = sum(1 for item in stats if item["status"] in {"ok", "skipped_existing"})
                    print(f"[progress] {i}/{len(symbols)} ok={ok} last={symbol} status={row['status']}", flush=True)
                    write_summary(staging_dir, stats)

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
