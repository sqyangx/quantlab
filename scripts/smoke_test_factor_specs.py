#!/usr/bin/env python3
"""Run sampled smoke tests for compiled factor-spec code."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quantlab.signal.factor_spec import load_sample_ohlcv, smoke_test_code_dir, write_smoke_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test compiled factor specs")
    parser.add_argument("--code-dir", required=True, help="Compiled factor code directory")
    parser.add_argument("--output", required=True, help="Smoke-test result CSV")
    parser.add_argument("--data-dir", default=None, help="Optional Qlib data dir; omit for synthetic data")
    parser.add_argument("--market", default="all", help="Qlib market")
    parser.add_argument("--anchor-date", default="2024-12-31", help="Anchor date for real data")
    parser.add_argument("--lookback-days", type=int, default=260, help="Lookback trading days")
    parser.add_argument("--sample-size", type=int, default=120, help="Sample symbol count")
    parser.add_argument("--timeout", type=int, default=60, help="Per-factor timeout seconds")
    parser.add_argument("--max-lines", type=int, default=220, help="Static code line limit")
    parser.add_argument("--sandbox", choices=["subprocess", "inprocess"], default="subprocess")
    args = parser.parse_args()

    ohlcv = load_sample_ohlcv(
        data_dir=args.data_dir,
        market=args.market,
        anchor_date=args.anchor_date,
        lookback_days=args.lookback_days,
        sample_size=args.sample_size,
    )
    rows = smoke_test_code_dir(args.code_dir, ohlcv, timeout_sec=args.timeout, sandbox=args.sandbox, max_lines=args.max_lines)
    write_smoke_results(args.output, rows)
    passed = sum(1 for row in rows if row.success)
    print(f"smoke passed: {passed}/{len(rows)} -> {args.output}")


if __name__ == "__main__":
    main()
