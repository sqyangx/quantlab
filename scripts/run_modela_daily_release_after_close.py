#!/usr/bin/env python3
"""Run the after-close Model-A release flow for one signal date."""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from pathlib import Path


DEFAULT_PYTHON = "/home/gpu/.conda/envs/asrlab/bin/python"
DEFAULT_PIPELINE_DIR = "quantlab/04_kronos_5min/2026/pipeline_5min_kronos_2026_gpu0_20260527_145447"
DEFAULT_DATA_DIR = "quantlab/02_data_5min/min_data"
DEFAULT_RELEASE_DIR = "quantlab/trading_strategy_release"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="收盘后生成 Model-A TradingAgents 发布页。")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="信号日期，例如 2026-06-01。")
    parser.add_argument("--python-bin", default=DEFAULT_PYTHON)
    parser.add_argument("--pipeline-dir", default=DEFAULT_PIPELINE_DIR)
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    parser.add_argument("--release-dir", default=DEFAULT_RELEASE_DIR)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--candidate-n", type=int, default=20)
    parser.add_argument("--final-n", type=int, default=5)
    parser.add_argument("--skip-first-flow", action="store_true", help="Kronos 15:00 产物已存在时跳过数据更新和推理。")
    parser.add_argument("--allow-signal-limit-up", action="store_true", help="诊断用：保留信号日 15:00 已涨停候选。")
    return parser.parse_args()


def run(cmd: list[str]) -> None:
    print("[cmd] " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def month_start(date_value: str) -> str:
    date = dt.date.fromisoformat(date_value)
    return date.replace(day=1).isoformat()


def main() -> None:
    args = parse_args()
    date_value = dt.date.fromisoformat(args.date).isoformat()
    month_key = date_value[:7].replace("-", "")
    release_dir = Path(args.release_dir)
    analysis_dir = release_dir / "data" / f"tradingagents_modela_rerank_{month_key}"
    portfolio_dir = release_dir / "data" / f"5min_modela_portfolio_backtest_{month_key}"
    frontend_dir = release_dir / "frontend" / f"tradingagents_modela_ui_{month_key}"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    portfolio_dir.mkdir(parents=True, exist_ok=True)
    frontend_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_first_flow:
        run(
            [
                args.python_bin,
                "-u",
                "scripts/run_5min_update_and_kronos.py",
                "--end",
                date_value,
                "--gpu",
                str(args.gpu),
                "--device",
                args.device,
                "--output-dir",
                args.pipeline_dir,
            ]
        )

    rerank_cmd = [
        args.python_bin,
        "-u",
        "scripts/tradingagents_modela_rerank.py",
        "--date",
        date_value,
        "--pipeline-dir",
        args.pipeline_dir,
        "--data-dir",
        args.data_dir,
        "--output-dir",
        str(analysis_dir),
        "--candidate-n",
        str(args.candidate_n),
        "--final-n",
        str(args.final_n),
    ]
    if args.allow_signal_limit_up:
        rerank_cmd.append("--allow-signal-limit-up")
    run(rerank_cmd)

    run(
        [
            args.python_bin,
            "-u",
            "scripts/backtest_5min_modela_portfolio.py",
            "--pipeline-dir",
            args.pipeline_dir,
            "--data-dir",
            args.data_dir,
            "--output-dir",
            str(portfolio_dir),
            "--start",
            month_start(date_value),
            "--end",
            date_value,
            "--top-n",
            str(args.final_n),
        ]
    )

    title = f"SmartStock AI · {date_value[:7]} Model-A 发布"
    run(
        [
            args.python_bin,
            "-u",
            str(release_dir / "tools" / "build_tradingagents_ui.py"),
            "--analysis-dir",
            str(analysis_dir),
            "--portfolio-dir",
            str(portfolio_dir),
            "--output-dir",
            str(frontend_dir),
            "--title",
            title,
        ]
    )

    print(f"[done] frontend={frontend_dir / 'index.html'}", flush=True)
    print(f"[done] analysis={analysis_dir}", flush=True)
    print(f"[done] portfolio={portfolio_dir}", flush=True)


if __name__ == "__main__":
    main()
