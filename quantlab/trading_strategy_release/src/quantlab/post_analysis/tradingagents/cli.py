"""Command line entrypoint for the standalone TradingAgents analysis module."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .core import run_analysis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对已有候选池执行 TradingAgents 二级分析。")
    parser.add_argument("--candidates-csv", required=True, help="候选池 CSV，至少包含 ticker；建议包含 model_a_score、candidate_rank。")
    parser.add_argument("--date", required=True, help="信号日期，例如 2026-05-25。")
    parser.add_argument("--output-dir", required=True, help="输出目录。")
    parser.add_argument("--data-dir", default="", help="可选 5min qlib 数据目录，用于计算日内技术证据。")
    parser.add_argument("--industry-map", default="", help="可选行业映射 CSV。")
    parser.add_argument("--cache-dir", default=".cache/tradingagents_external_cache")
    parser.add_argument("--final-n", type=int, default=5)
    parser.add_argument("--fetch-external", action="store_true", help="实际请求财报、公告、新闻。")
    parser.add_argument("--request-timeout", type=float, default=8.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    return parser.parse_args()


def optional_path(value: str) -> Path | None:
    return Path(value) if value else None


def main() -> None:
    args = parse_args()
    candidates = pd.read_csv(args.candidates_csv)
    payload = run_analysis(
        candidates=candidates,
        date=args.date,
        output_dir=Path(args.output_dir),
        data_dir=optional_path(args.data_dir),
        industry_map_path=optional_path(args.industry_map),
        cache_dir=Path(args.cache_dir),
        final_n=args.final_n,
        fetch_external=args.fetch_external,
        request_timeout=args.request_timeout,
        sleep_seconds=args.sleep_seconds,
    )
    print(f"[done] {Path(args.output_dir) / f'{args.date}_analysis.json'}")
    print("final_tickers=" + ",".join(payload["final_tickers"]))


if __name__ == "__main__":
    main()
