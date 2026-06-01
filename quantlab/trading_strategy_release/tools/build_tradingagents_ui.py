#!/usr/bin/env python3
"""Build a static UI for TradingAgents post-selection analysis outputs."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_ANALYSIS_DIR = "quantlab/07_stock_selection_strategies/tradingagents_modela_rerank_20260525_20260529_fetch_baostock"
DEFAULT_PORTFOLIO_DIR = "quantlab/07_stock_selection_strategies/5min_modela_portfolio_backtest_20260525_20260529"
DEFAULT_OUTPUT_DIR = "quantlab/07_stock_selection_strategies/tradingagents_modela_ui_20260525_20260529"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 TradingAgents 二级分析静态前端。")
    parser.add_argument("--analysis-dir", default=DEFAULT_ANALYSIS_DIR)
    parser.add_argument("--portfolio-dir", default=DEFAULT_PORTFOLIO_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--title", default="Model-A × TradingAgents 5min 选股分析")
    return parser.parse_args()


def esc(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return html.escape(str(value), quote=True)


def fmt_num(value: Any, digits: int = 3) -> str:
    try:
        number = float(value)
    except Exception:
        return "暂无"
    if not math.isfinite(number):
        return "暂无"
    return f"{number:.{digits}f}"


def fmt_pct(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except Exception:
        return "暂无"
    if not math.isfinite(number):
        return "暂无"
    return f"{number * 100:.{digits}f}%"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def short_text(value: Any, limit: int = 72) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def load_analysis(analysis_dir: Path) -> list[dict[str, Any]]:
    payloads = []
    for path in sorted(analysis_dir.glob("*_analysis.json")):
        payloads.append(json.loads(path.read_text(encoding="utf-8")))
    return payloads


def top_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(payload.get("candidates", []))[: int(payload.get("final_n", 5))]


def risk_class(level: str) -> str:
    return {"高": "danger", "中": "warn", "低": "ok"}.get(level, "neutral")


def score_bar(label: str, value: Any, class_name: str = "") -> str:
    try:
        number = max(0.0, min(1.0, float(value)))
    except Exception:
        number = 0.0
    return f"""
    <div class="score-row {class_name}">
      <span>{esc(label)}</span>
      <div class="meter"><i style="width:{number * 100:.1f}%"></i></div>
      <b>{number:.3f}</b>
    </div>
    """


def metric_card(label: str, value: str, hint: str = "") -> str:
    return f"""
    <section class="metric">
      <i></i>
      <span>{esc(label)}</span>
      <strong>{esc(value)}</strong>
      <em>{esc(hint)}</em>
    </section>
    """


def evidence_titles(items: list[dict[str, Any]], limit: int = 3) -> str:
    titles = [clean_text(x.get("title")) for x in items if clean_text(x.get("title"))]
    if not titles:
        return '<li class="muted">暂无可展示证据</li>'
    return "\n".join(f"<li>{esc(short_text(title, 86))}</li>" for title in titles[:limit])


def event_theme(items: list[dict[str, Any]]) -> str:
    titles = [clean_text(x.get("title")) for x in items if clean_text(x.get("title"))]
    joined = "；".join(titles[:5])
    if not joined:
        return "暂无明确事件线索"
    if "龙虎榜" in joined:
        return "短线资金活跃，龙虎榜信息较多，需要重点关注波动和换手。"
    if "异常波动" in joined:
        return "出现交易异常波动相关公告，短期价格波动风险较高。"
    if "股东" in joined or "股东会" in joined:
        return "公告以公司治理和股东会议事项为主，对短线交易更多是信息披露背景。"
    if "减持" in joined:
        return "存在减持相关线索，需要降低事件面评分。"
    if "中标" in joined or "订单" in joined or "合作" in joined:
        return "存在业务订单或合作线索，对基本面预期有一定支撑。"
    return "事件信息以常规公告和媒体报道为主，需结合价格行为确认。"


def human_readable_analysis(item: dict[str, Any]) -> dict[str, Any]:
    scores = item.get("scores", {})
    ev = item.get("external_evidence", {})
    tech = item.get("technical_features", {})
    sentiment = ev.get("sentiment") or {}
    announcements = ev.get("announcements") or []
    news = ev.get("news") or []
    ticker = item.get("ticker", "")
    rank = item.get("candidate_rank", "")
    risk = scores.get("risk_level", "未知")
    final_score = fmt_num(scores.get("final_score"))
    quant_score = fmt_num(scores.get("quant_score"))
    tech_score = fmt_num(scores.get("technical_score"))
    day_ret = fmt_pct(tech.get("day_return"))
    last_hour = fmt_pct(tech.get("last_hour_return"))
    pos = sentiment.get("positive_hits", 0)
    neg = sentiment.get("negative_hits", 0)
    event_line = event_theme([*announcements, *news])
    st_flag = any("ST" in clean_text(x.get("title")).upper() for x in [*announcements, *news])
    risk_note = "该股标题中出现 ST 相关信息，必须按高波动和高不确定性处理。" if st_flag else "未看到必须单独剔除的重大负面标题，但仍需结合成交量和次日价格确认。"
    conclusion = (
        f"{ticker} 是 Model-A 候选池中的第 {rank} 名，二级分析最终分 {final_score}。"
        f"量化分 {quant_score}，技术分 {tech_score}，说明它主要是由模型信号和盘面行为共同推上来。"
    )
    return {
        "summary": conclusion,
        "market": f"信号日下午收盘前日内表现为 {day_ret}，最后一小时为 {last_hour}。如果最后一小时走强，说明短线资金仍在承接；如果走弱，则应降低追高预期。",
        "event": f"公告和新闻的可读结论：{event_line} 情绪命中正向 {pos} 次、负向 {neg} 次，不能简单理解为利好或利空，需要看次日资金是否继续确认。",
        "risk": f"风险等级为 {risk}。{risk_note}",
        "action": "发布建议：保留在候选观察池，实盘发布时应同时给出买入计划、止损条件和隔日复盘结论；该页面当前展示的是投研解释层，后续可替换为大模型生成的最终表述。",
    }


def human_analysis_panel(item: dict[str, Any]) -> str:
    analysis = human_readable_analysis(item)
    return f"""
    <section class="panel readable-panel">
      <h3>投研解读</h3>
      <p>{esc(analysis['summary'])}</p>
      <p>{esc(analysis['market'])}</p>
      <p>{esc(analysis['event'])}</p>
      <p>{esc(analysis['risk'])}</p>
      <p class="action-note">{esc(analysis['action'])}</p>
    </section>
    """


def agent_grid(report: dict[str, str]) -> str:
    preferred = ["量化证据分析师", "技术分析师", "基本面分析师", "看多研究员", "看空研究员", "交易员结论"]
    cards = []
    for role in preferred:
        text = report.get(role)
        if not text:
            continue
        cards.append(
            f"""
            <article class="agent-card">
              <span>{esc(role)}</span>
              <p>{esc(clean_text(text))}</p>
            </article>
            """
        )
    return "\n".join(cards)


def stock_panel(item: dict[str, Any]) -> str:
    scores = item.get("scores", {})
    ev = item.get("external_evidence", {})
    tech = item.get("technical_features", {})
    fin = ev.get("financial") or {}
    sentiment = ev.get("sentiment") or {}
    announcements = ev.get("announcements") or []
    news = ev.get("news") or []
    ticker = item.get("ticker", "")
    level = scores.get("risk_level", "")
    return f"""
    <article class="stock-panel" id="{esc(ticker)}">
      <header class="stock-head">
        <div>
          <span class="rank-chip">TA #{esc(item.get('final_rank', '')) or ''}</span>
          <h2>{esc(ticker)}</h2>
          <p>{esc(scores.get('industry', '未知行业'))} · Model-A #{esc(item.get('candidate_rank', ''))}</p>
        </div>
        <div class="signal-stack">
          <span>QUANT</span>
          <b>{fmt_num(scores.get('quant_score'))}</b>
          <span>TECH</span>
          <b>{fmt_num(scores.get('technical_score'))}</b>
        </div>
        <div class="score-orb">
          <strong>{fmt_num(scores.get('final_score'))}</strong>
          <span>FINAL</span>
        </div>
      </header>
      <div class="stock-grid">
        <section class="panel scores">
          <h3>五维评分</h3>
          {score_bar('量化证据', scores.get('quant_score'), 'cyan')}
          {score_bar('技术形态', scores.get('technical_score'), 'green')}
          {score_bar('基本面', scores.get('fundamental_score'), 'amber')}
          {score_bar('新闻情绪', scores.get('event_sentiment_score'), 'pink')}
          {score_bar('看空风险', scores.get('bear_risk_score'), 'red')}
        </section>
        <section class="panel facts">
          <h3>核心证据</h3>
          <dl>
            <dt>日内涨跌</dt><dd>{fmt_pct(tech.get('day_return'))}</dd>
            <dt>最后一小时</dt><dd>{fmt_pct(tech.get('last_hour_return'))}</dd>
            <dt>ROE</dt><dd>{esc(fin.get('roe') or '暂无')}</dd>
            <dt>毛利率</dt><dd>{esc(fin.get('gross_margin') or '暂无')}</dd>
            <dt>情绪命中</dt><dd>正 {esc(sentiment.get('positive_hits', 0))} / 负 {esc(sentiment.get('negative_hits', 0))}</dd>
          </dl>
          <span class="risk {risk_class(str(level))}">风险 {esc(level or '未知')}</span>
        </section>
      </div>
      <section class="panel agent-section">
        <h3>多智能体观点</h3>
        {human_analysis_panel(item)}
        <div class="agent-grid">{agent_grid(item.get('agent_report', {}))}</div>
      </section>
      <section class="evidence-grid">
        <div class="panel">
          <h3>公告</h3>
          <ul>{evidence_titles(announcements)}</ul>
        </div>
        <div class="panel">
          <h3>新闻</h3>
          <ul>{evidence_titles(news)}</ul>
        </div>
      </section>
    </article>
    """


def date_page(
    payload: dict[str, Any],
    output_dir: Path,
    trades: pd.DataFrame,
    skipped: pd.DataFrame,
    selection_records: pd.DataFrame,
    title: str,
) -> None:
    date = str(payload["date"])
    ranked = []
    for idx, item in enumerate(top_items(payload), start=1):
        item = dict(item)
        item["final_rank"] = idx
        ranked.append(item)

    day_selections = selection_records[selection_records.get("signal_date", pd.Series(dtype=str)).astype(str) == date] if not selection_records.empty else pd.DataFrame()
    day_trades = pd.DataFrame()
    if not day_selections.empty and not trades.empty:
        keys = day_selections[["ticker", "planned_entry_date", "planned_exit_date"]].copy()
        day_trades = trades.merge(keys, on="ticker", how="inner")
        day_trades = day_trades[
            (day_trades["entry_time"].astype(str).str[:10] == day_trades["planned_entry_date"].astype(str))
            & (day_trades["exit_time"].astype(str).str[:10] == day_trades["planned_exit_date"].astype(str))
        ]
    day_skipped = skipped[skipped.get("signal_time", pd.Series(dtype=str)).astype(str).str[:10] == date] if not skipped.empty else pd.DataFrame()

    trade_rows = []
    for _, row in day_trades.iterrows():
        trade_rows.append(
            f"""
            <tr>
              <td>{esc(row.get('ticker'))}</td>
              <td>{esc(row.get('entry_time'))}</td>
              <td>{fmt_num(row.get('entry_price'))}</td>
              <td>{esc(row.get('exit_time'))}</td>
              <td>{fmt_num(row.get('exit_price'))}</td>
              <td class="{ 'pos' if float(row.get('pnl', 0)) >= 0 else 'neg' }">{fmt_pct(row.get('return'))}</td>
            </tr>
            """
        )
    if not trade_rows:
        trade_rows.append('<tr><td colspan="6" class="muted">当日信号尚无已完成成交，或因持仓占用跳过。</td></tr>')

    skipped_text = "；".join(day_skipped["reason"].astype(str).tolist()) if not day_skipped.empty else "无"
    nav_links = "\n".join(
        f'<a href="#{esc(item.get("ticker"))}">#{idx} {esc(item.get("ticker"))}</a>' for idx, item in enumerate(ranked, start=1)
    )
    body = f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{esc(title)} · {esc(date)}</title>
      <link rel="stylesheet" href="style.css">
    </head>
    <body>
      <div class="app-frame">
        <aside class="side-nav">
          <div class="brand-mark"><b>SmartStock AI</b><span>5min Model-A</span></div>
          <a class="active" href="index.html">推荐看板</a>
          <a href="index.html#watchlist">观察列表</a>
          <a href="index.html#market">市场趋势</a>
          <a href="index.html#analytics">高级分析</a>
        </aside>
        <main class="shell">
        <nav class="top-nav">
          <a href="index.html">总览</a>
          <label class="search-box">Search selected stocks...</label>
          <span>{esc(date)}</span>
        </nav>
        <header class="hero compact">
          <div>
            <span class="eyebrow">交易日 {esc(date)}</span>
            <h1>TradingAgents 建议 Top5</h1>
            <p>前置 Model-A 只生成 top20 候选，本页展示独立后处理模块的二次分析、证据和讨论结论。</p>
          </div>
          <div class="mission-panel">
            <div class="scanner"></div>
            <span>ACTIVE WATCHLIST</span>
            <div class="mini-nav">{nav_links}</div>
          </div>
        </header>
        <section class="trade-strip">
          <div>
            <span>基准组合成交说明</span>
            <strong>Model-A top5 组合回测</strong>
            <em>TradingAgents top5 是二级建议，成交记录展示的是当前基准流程，二者分开展示。</em>
          </div>
          <div>
            <span>跳过原因</span>
            <strong>{esc(skipped_text)}</strong>
          </div>
        </section>
        <section class="panel">
          <h3>实际成交与收益</h3>
          <div class="table-wrap">
            <table>
              <thead><tr><th>股票</th><th>买入时间</th><th>买入价</th><th>卖出时间</th><th>卖出价</th><th>收益</th></tr></thead>
              <tbody>{''.join(trade_rows)}</tbody>
            </table>
          </div>
        </section>
        {''.join(stock_panel(item) for item in ranked)}
        </main>
      </div>
    </body>
    </html>
    """
    (output_dir / f"{date}.html").write_text(body, encoding="utf-8")


def sparkline(points: list[float]) -> str:
    if not points:
        return ""
    low, high = min(points), max(points)
    span = high - low if high > low else 1.0
    coords = []
    width, height = 520, 130
    for idx, value in enumerate(points):
        x = idx * width / max(1, len(points) - 1)
        y = height - ((value - low) / span * (height - 16) + 8)
        coords.append(f"{x:.1f},{y:.1f}")
    return " ".join(coords)


def index_page(
    payloads: list[dict[str, Any]],
    output_dir: Path,
    summary: dict[str, Any],
    equity: pd.DataFrame,
    title: str,
) -> None:
    days = [str(p["date"]) for p in payloads]
    all_items = [item for payload in payloads for item in top_items(payload)]
    avg_score = sum(float(x.get("scores", {}).get("final_score", 0.0)) for x in all_items) / max(1, len(all_items))
    nav_cards = []
    for payload in payloads:
        date = str(payload["date"])
        items = top_items(payload)
        tickers = [str(x.get("ticker")) for x in items]
        mean_score = sum(float(x.get("scores", {}).get("final_score", 0.0)) for x in items) / max(1, len(items))
        risk_levels = [str(x.get("scores", {}).get("risk_level", "未知")) for x in items]
        risk_text = " / ".join(sorted(set(risk_levels)))
        ticker_chips = "".join(f"<span>{esc(t)}</span>" for t in tickers)
        nav_cards.append(
            f"""
            <a class="day-card" href="{esc(date)}.html">
              <span>{esc(date)}</span>
              <strong>{fmt_num(mean_score)}</strong>
              <em>平均最终分 · 风险 {esc(risk_text)}</em>
              <div class="ticker-cloud">{ticker_chips}</div>
            </a>
            """
        )

    nav_points = equity["nav"].astype(float).tolist() if not equity.empty and "nav" in equity else []
    polyline = sparkline(nav_points)
    end_nav = summary.get("end_nav", "")
    total_return = summary.get("total_return", "")
    completed = summary.get("completed_trades", "")
    skipped = summary.get("skipped_entries", "")
    body = f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{esc(title)}</title>
      <link rel="stylesheet" href="style.css">
    </head>
    <body>
      <div class="app-frame">
        <aside class="side-nav">
          <div class="brand-mark"><b>SmartStock AI</b><span>5min Model-A</span></div>
          <a class="active" href="index.html">推荐看板</a>
          <a href="#watchlist">观察列表</a>
          <a href="#market">市场趋势</a>
          <a href="#analytics">高级分析</a>
        </aside>
        <main class="shell">
        <nav class="top-nav">
          <label class="search-box">Search selected stocks...</label>
          <span>TradingAgents 二级分析</span>
        </nav>
        <header class="hero">
          <div>
            <span class="eyebrow">{esc(days[0])} 至 {esc(days[-1])}</span>
            <h1>{esc(title)}</h1>
            <p>Model-A 从全市场选择 top20 候选，TradingAgents 后处理模块接入财报、公告、新闻、情绪和 5min 技术证据，输出最终建议 top5。</p>
          </div>
          <section class="hero-board">
            <div class="scanner"></div>
            <span>Pipeline</span>
            <strong>Model-A top20 → 多智能体分析 → 建议 top5</strong>
            <em>后处理模块已独立于实验脚本，可作为发布代码单独集成。</em>
          </section>
        </header>
        <section class="metrics-grid">
          {metric_card('覆盖交易日', str(len(days)), ', '.join(days))}
          {metric_card('建议股票数', str(len(all_items)), f'平均最终分 {avg_score:.3f}')}
          {metric_card('基准组合收益', fmt_pct(total_return), f'期末净值 {fmt_num(end_nav, 2)}')}
          {metric_card('成交/跳过', f'{esc(completed)} / {esc(skipped)}', '资金占用逻辑已纳入回测')}
        </section>
        <section class="dashboard-grid">
          <div class="panel equity-panel">
            <h3>账户净值曲线</h3>
            <svg viewBox="0 0 520 150" role="img" aria-label="账户净值曲线">
              <defs>
                <linearGradient id="lineGlow" x1="0" x2="1">
                  <stop offset="0" stop-color="#31d5ff"/>
                  <stop offset="1" stop-color="#72f6a8"/>
                </linearGradient>
              </defs>
              <polyline points="{esc(polyline)}" fill="none" stroke="url(#lineGlow)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <p>该曲线来自 Model-A 基准组合回测，用于展示资金占用后的真实账户路径。</p>
          </div>
          <div class="panel module-panel">
            <h3>独立模块边界</h3>
            <ol>
              <li>上游只传入候选池 DataFrame 或 CSV。</li>
              <li>后处理模块负责证据获取、分析、排序和报告。</li>
              <li>UI 只读取后处理产物，不导入实验代码。</li>
            </ol>
          </div>
        </section>
        <section class="days-grid">
          {''.join(nav_cards)}
        </section>
        </main>
      </div>
    </body>
    </html>
    """
    (output_dir / "index.html").write_text(body, encoding="utf-8")


def write_css(output_dir: Path) -> None:
    css = """
:root {
  color-scheme: dark;
  --bg: #04070d;
  --panel: rgba(8, 16, 31, 0.78);
  --panel-2: rgba(13, 27, 49, 0.82);
  --panel-3: rgba(2, 9, 18, 0.72);
  --line: rgba(86, 220, 255, 0.32);
  --line-hot: rgba(123, 247, 196, 0.74);
  --text: #f1fbff;
  --muted: #8ea9c4;
  --cyan: #24d8ff;
  --green: #7bf7c4;
  --amber: #ffd36e;
  --pink: #ff6fd8;
  --red: #ff6374;
  --violet: #8d7dff;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  min-height: 100vh;
  color: var(--text);
  font-family: Inter, "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
  background:
    linear-gradient(rgba(36, 216, 255, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(36, 216, 255, 0.045) 1px, transparent 1px),
    radial-gradient(circle at 15% 0%, rgba(36, 216, 255, 0.24), transparent 32rem),
    radial-gradient(circle at 82% 6%, rgba(123, 247, 196, 0.18), transparent 30rem),
    radial-gradient(circle at 55% 95%, rgba(141, 125, 255, 0.14), transparent 36rem),
    linear-gradient(180deg, #04070d 0%, #07101d 52%, #04070d 100%);
  background-size: 36px 36px, 36px 36px, auto, auto, auto, auto;
  overflow-x: hidden;
}
body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background:
    linear-gradient(120deg, transparent 0 38%, rgba(36, 216, 255, 0.08) 44%, transparent 52%),
    repeating-linear-gradient(180deg, rgba(255,255,255,0.025) 0 1px, transparent 1px 7px);
  mix-blend-mode: screen;
  opacity: .68;
}
body::after {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  box-shadow: inset 0 0 160px rgba(0, 0, 0, 0.86);
}
.shell { position: relative; z-index: 1; width: min(1500px, calc(100% - 44px)); margin: 0 auto; padding: 28px 0 72px; }
a { color: inherit; text-decoration: none; }
.top-nav { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; color: var(--muted); font-size: 13px; }
.top-nav a { color: var(--cyan); border: 1px solid rgba(36,216,255,.25); padding: 8px 12px; border-radius: 6px; background: rgba(36,216,255,.06); }
.hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  gap: 24px;
  align-items: stretch;
  min-height: 360px;
  padding: 42px;
  border: 1px solid var(--line);
  background:
    linear-gradient(135deg, rgba(36,216,255,.22), transparent 28%, rgba(123,247,196,.10) 58%, rgba(141,125,255,.16)),
    repeating-linear-gradient(90deg, rgba(255,255,255,.035) 0 1px, transparent 1px 84px),
    rgba(5, 12, 24, 0.88);
  box-shadow:
    0 0 0 1px rgba(255,255,255,.035) inset,
    0 30px 90px rgba(0, 0, 0, 0.52),
    0 0 68px rgba(36, 216, 255, 0.13);
  border-radius: 8px;
  overflow: hidden;
  backdrop-filter: blur(18px);
}
.hero::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(36,216,255,.55), transparent 18%, transparent 82%, rgba(123,247,196,.45)),
    linear-gradient(180deg, rgba(255,255,255,.16), transparent 12%, transparent 86%, rgba(36,216,255,.22));
  opacity: .25;
  pointer-events: none;
}
.hero > * { position: relative; z-index: 1; }
.hero::after {
  content: "MODEL-A / TRADINGAGENTS / 5MIN / POST ANALYSIS";
  position: absolute;
  right: 24px;
  bottom: 14px;
  color: rgba(241,251,255,.13);
  font-size: 12px;
  letter-spacing: 0;
}
.hero.compact { min-height: 280px; grid-template-columns: minmax(0, 1fr) 430px; }
.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  color: var(--green);
  font-size: 13px;
  letter-spacing: 0;
  text-transform: uppercase;
}
.eyebrow::before {
  content: "";
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 18px var(--green);
}
h1 {
  margin: 18px 0 16px;
  max-width: 920px;
  font-size: clamp(42px, 5.4vw, 82px);
  line-height: .96;
  letter-spacing: 0;
  text-shadow: 0 0 34px rgba(36,216,255,.22);
}
h2 { margin: 8px 0 6px; font-size: 38px; letter-spacing: 0; text-shadow: 0 0 28px rgba(36,216,255,.22); }
h3 { margin: 0 0 18px; font-size: 17px; letter-spacing: 0; }
p { color: #bad0e8; line-height: 1.72; }
.hero-board, .metric, .panel, .day-card, .trade-strip, .stock-panel {
  position: relative;
  border: 1px solid var(--line);
  background:
    linear-gradient(180deg, rgba(255,255,255,.065), rgba(255,255,255,.018)),
    var(--panel);
  border-radius: 8px;
  box-shadow: 0 20px 62px rgba(0, 0, 0, 0.34), inset 0 0 0 1px rgba(255,255,255,.025);
  backdrop-filter: blur(16px);
}
.hero-board::before, .metric::before, .panel::before, .day-card::before, .trade-strip::before, .stock-panel::before {
  content: "";
  position: absolute;
  left: 12px;
  right: 12px;
  top: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(36,216,255,.88), transparent);
}
.hero-board::after, .panel::after, .stock-panel::after {
  content: "";
  position: absolute;
  width: 9px;
  height: 9px;
  right: 12px;
  top: 12px;
  border-top: 1px solid var(--line-hot);
  border-right: 1px solid var(--line-hot);
}
.hero-board { padding: 28px; align-self: end; }
.hero-board span, .metric span, .trade-strip span, .day-card span, .agent-card span { display: block; color: var(--muted); font-size: 13px; }
.hero-board strong { display: block; margin: 16px 0; font-size: 24px; line-height: 1.3; }
.hero-board em, .metric em, .day-card em, .trade-strip em { color: var(--muted); font-style: normal; line-height: 1.6; }
.scanner {
  height: 4px;
  margin-bottom: 22px;
  border-radius: 999px;
  background: linear-gradient(90deg, transparent, var(--cyan), var(--green), transparent);
  box-shadow: 0 0 24px rgba(36,216,255,.45);
}
.metrics-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin: 18px 0; }
.metric { min-height: 142px; padding: 22px; overflow: hidden; }
.metric i {
  position: absolute;
  width: 48px;
  height: 48px;
  right: 18px;
  top: 18px;
  border: 1px solid rgba(36,216,255,.28);
  border-radius: 50%;
  box-shadow: inset 0 0 18px rgba(36,216,255,.14), 0 0 22px rgba(36,216,255,.10);
}
.metric i::before {
  content: "";
  position: absolute;
  inset: 10px;
  border-radius: 50%;
  border: 1px solid rgba(123,247,196,.34);
}
.metric strong { display: block; margin: 16px 0 8px; font-size: 34px; color: var(--cyan); text-shadow: 0 0 22px rgba(36,216,255,.32); }
.dashboard-grid { display: grid; grid-template-columns: 1.35fr 0.65fr; gap: 18px; margin-bottom: 18px; }
.panel { padding: 24px; }
.equity-panel svg {
  width: 100%;
  height: 190px;
  border-bottom: 1px solid rgba(255,255,255,0.07);
  background:
    linear-gradient(rgba(36,216,255,.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(36,216,255,.06) 1px, transparent 1px);
  background-size: 34px 34px;
}
.module-panel ol { margin: 0; padding-left: 20px; color: #c8d5e8; line-height: 1.9; }
.days-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 16px; }
.day-card { min-height: 230px; padding: 20px; transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease; overflow: hidden; }
.day-card:hover { transform: translateY(-5px); border-color: rgba(36, 216, 255, 0.82); box-shadow: 0 24px 72px rgba(0,0,0,.42), 0 0 42px rgba(36,216,255,.16); }
.day-card strong { display: block; margin: 12px 0 8px; font-size: 44px; color: var(--green); text-shadow: 0 0 24px rgba(123,247,196,.32); }
.day-card::after {
  content: "";
  position: absolute;
  right: -28px;
  bottom: -28px;
  width: 120px;
  height: 120px;
  border: 1px solid rgba(36,216,255,.16);
  transform: rotate(45deg);
}
.ticker-cloud { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
.ticker-cloud span, .rank-chip, .risk {
  border: 1px solid rgba(36,216,255,0.28);
  border-radius: 999px;
  padding: 6px 10px;
  color: #dce9f8;
  background: rgba(36,216,255,0.07);
  font-size: 12px;
  box-shadow: inset 0 0 14px rgba(36,216,255,.06);
}
.mini-nav { display: flex; flex-wrap: wrap; gap: 10px; align-content: end; }
.mission-panel {
  border: 1px solid rgba(36,216,255,.28);
  border-radius: 8px;
  padding: 24px;
  background: rgba(2,9,18,.48);
  align-self: end;
}
.mission-panel > span { display: block; margin-bottom: 14px; color: var(--muted); font-size: 12px; }
.mini-nav a { padding: 10px 12px; border: 1px solid var(--line); border-radius: 999px; color: var(--cyan); background: rgba(36,216,255,0.06); box-shadow: 0 0 18px rgba(36,216,255,.08); }
.trade-strip { margin: 18px 0; padding: 22px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.trade-strip strong { display: block; margin: 8px 0; font-size: 20px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; min-width: 760px; }
th, td { padding: 14px 12px; border-bottom: 1px solid rgba(255,255,255,0.08); text-align: left; white-space: nowrap; }
th { color: var(--muted); font-weight: 500; background: rgba(36,216,255,.035); }
tr:hover td { background: rgba(36,216,255,.035); }
.pos { color: var(--green); text-shadow: 0 0 16px rgba(123,247,196,.25); }
.neg { color: var(--red); text-shadow: 0 0 16px rgba(255,99,116,.25); }
.muted { color: var(--muted); }
.stock-panel { margin-top: 22px; padding: 0; overflow: hidden; }
.stock-head {
  display: grid;
  grid-template-columns: 1fr 150px 128px;
  gap: 20px;
  align-items: center;
  padding: 30px;
  background:
    linear-gradient(90deg, rgba(36,216,255,0.18), rgba(123,247,196,0.06) 54%, rgba(255,255,255,0.02)),
    repeating-linear-gradient(90deg, transparent 0 78px, rgba(255,255,255,.035) 78px 79px);
}
.stock-head p { margin: 0; }
.signal-stack {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px 12px;
  padding: 16px;
  border: 1px solid rgba(36,216,255,.22);
  border-radius: 8px;
  background: rgba(2,9,18,.42);
}
.signal-stack span { color: var(--muted); font-size: 11px; }
.signal-stack b { color: var(--green); font-weight: 700; }
.score-orb {
  width: 118px;
  height: 118px;
  border-radius: 50%;
  display: grid;
  place-content: center;
  text-align: center;
  border: 1px solid rgba(36, 216, 255, 0.62);
  background: radial-gradient(circle, rgba(36,216,255,.20), rgba(2,9,18,.58) 62%, rgba(123,247,196,.10));
  box-shadow: 0 0 44px rgba(36, 216, 255, 0.24), inset 0 0 24px rgba(123,247,196,.10);
}
.score-orb strong { font-size: 28px; color: var(--green); }
.score-orb span { color: var(--muted); font-size: 12px; }
.stock-grid, .evidence-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; padding: 18px; }
.agent-section { margin: 0 18px 18px; }
.score-row { display: grid; grid-template-columns: 86px 1fr 56px; align-items: center; gap: 10px; margin: 14px 0; color: #cfdaea; }
.meter { height: 11px; background: rgba(255,255,255,0.08); border-radius: 999px; overflow: hidden; box-shadow: inset 0 0 10px rgba(0,0,0,.35); }
.meter i { display: block; height: 100%; background: var(--cyan); border-radius: inherit; box-shadow: 0 0 16px currentColor; }
.score-row.green .meter i { background: var(--green); }
.score-row.amber .meter i { background: var(--amber); }
.score-row.pink .meter i { background: var(--pink); }
.score-row.red .meter i { background: var(--red); }
dl { display: grid; grid-template-columns: 110px 1fr; gap: 12px 14px; margin: 0 0 18px; }
dt { color: var(--muted); }
dd { margin: 0; }
.risk.ok { color: var(--green); border-color: rgba(114,246,168,0.4); }
.risk.warn { color: var(--amber); border-color: rgba(255,209,102,0.4); }
.risk.danger { color: var(--red); border-color: rgba(255,95,109,0.4); }
.agent-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.agent-card {
  min-height: 150px;
  padding: 16px;
  border: 1px solid rgba(36,216,255,0.16);
  border-radius: 8px;
  background:
    linear-gradient(160deg, rgba(36,216,255,.08), rgba(255,255,255,.018) 48%, rgba(123,247,196,.045)),
    var(--panel-2);
}
.agent-card p { margin: 10px 0 0; font-size: 13px; line-height: 1.65; }
ul { margin: 0; padding-left: 18px; color: #cbd8e8; line-height: 1.8; }
@media (max-width: 1100px) {
  .hero, .hero.compact, .dashboard-grid, .stock-grid, .evidence-grid, .trade-strip, .stock-head { grid-template-columns: 1fr; }
  .metrics-grid, .days-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .agent-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
  .shell { width: min(100% - 24px, 1440px); padding-top: 14px; }
  .hero { padding: 24px; }
  h1 { font-size: 38px; }
  .metrics-grid, .days-grid, .agent-grid { grid-template-columns: 1fr; }
  .stock-head { align-items: flex-start; flex-direction: column; }
}

/* SmartStock AI light terminal skin, aligned to the provided references. */
:root {
  color-scheme: light;
  --bg: #eef3f7;
  --panel: #ffffff;
  --panel-2: #f8fafc;
  --panel-3: #eef2f6;
  --line: #d7dee7;
  --line-hot: #c20d17;
  --text: #0d141c;
  --muted: #667484;
  --cyan: #2267b8;
  --green: #087c32;
  --amber: #d99100;
  --pink: #ad285f;
  --red: #c20d17;
  --violet: #2f5fb5;
}
body {
  color: var(--text);
  background:
    radial-gradient(circle at 78% 12%, rgba(194, 13, 23, 0.10), transparent 26rem),
    radial-gradient(circle at 12% 82%, rgba(34, 103, 184, 0.12), transparent 30rem),
    linear-gradient(180deg, #f8fbfd 0%, #edf2f6 100%);
  background-size: auto;
}
body::before {
  opacity: .72;
  background:
    linear-gradient(90deg, rgba(255,255,255,.74), rgba(255,255,255,.20)),
    radial-gradient(circle at 70% 16%, rgba(0,0,0,.08), transparent 14rem);
  backdrop-filter: blur(0);
}
body::after { box-shadow: inset 0 0 120px rgba(102,116,132,.16); }
.app-frame {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 228px minmax(0, 1fr);
  min-height: 100vh;
}
.side-nav {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 22px 14px;
  border-right: 1px solid #dbe2ea;
  background: rgba(255,255,255,.82);
  backdrop-filter: blur(18px);
  box-shadow: 12px 0 42px rgba(40, 55, 74, .08);
}
.brand-mark {
  display: grid;
  gap: 4px;
  margin: 0 8px 22px;
  font-size: 18px;
}
.brand-mark::before {
  content: "";
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: linear-gradient(135deg, #2f5fb5, #d91624);
  box-shadow: 0 10px 24px rgba(47,95,181,.24);
}
.brand-mark span { color: var(--muted); font-size: 12px; }
.side-nav a {
  display: block;
  margin: 7px 0;
  padding: 12px 14px;
  border-radius: 8px;
  color: #17212c;
  font-size: 14px;
}
.side-nav a.active, .side-nav a:hover {
  background: #eef2f6;
  box-shadow: inset 3px 0 0 #c20d17;
}
.shell {
  width: min(1320px, calc(100% - 32px));
  padding: 12px 0 54px;
}
.top-nav {
  height: 48px;
  margin-bottom: 18px;
  padding: 0 6px;
  color: #1b2633;
}
.top-nav a {
  color: #1b2633;
  border-color: #d8e0e8;
  background: #fff;
  box-shadow: 0 8px 18px rgba(39, 51, 68, .08);
}
.search-box {
  flex: 0 1 360px;
  padding: 12px 16px;
  border-radius: 8px;
  color: #7a8796;
  background: #eef2f6;
  border: 1px solid #dce3eb;
}
.hero, .hero.compact {
  min-height: 240px;
  padding: 26px;
  border-color: #d5dde6;
  background:
    linear-gradient(135deg, rgba(255,255,255,.96), rgba(242,246,250,.88)),
    radial-gradient(circle at 84% 24%, rgba(194,13,23,.10), transparent 16rem);
  box-shadow: 0 16px 34px rgba(39, 51, 68, .12);
  backdrop-filter: blur(18px);
}
.hero::before {
  background:
    linear-gradient(90deg, rgba(194,13,23,.32), transparent 20%, transparent 80%, rgba(47,95,181,.24)),
    linear-gradient(180deg, rgba(255,255,255,.65), transparent);
  opacity: .20;
}
.hero::after {
  color: rgba(13,20,28,.10);
}
.eyebrow { color: #2267b8; }
.eyebrow::before { background: #2267b8; box-shadow: 0 0 12px rgba(34,103,184,.32); }
h1 {
  max-width: 760px;
  color: #111820;
  font-size: clamp(34px, 4vw, 56px);
  text-shadow: none;
}
h2 {
  color: #0b1118;
  text-shadow: none;
}
p { color: #4d5b6b; }
.hero-board, .metric, .panel, .day-card, .trade-strip, .stock-panel {
  border: 1px solid #d4dce5;
  background: #ffffff;
  box-shadow: 0 14px 30px rgba(39, 51, 68, .13);
  backdrop-filter: none;
}
.hero-board::before, .metric::before, .panel::before, .day-card::before, .trade-strip::before, .stock-panel::before {
  background: linear-gradient(90deg, transparent, rgba(194,13,23,.52), transparent);
}
.hero-board::after, .panel::after, .stock-panel::after { display: none; }
.scanner {
  height: 3px;
  background: linear-gradient(90deg, transparent, #d91624, #2f5fb5, transparent);
  box-shadow: 0 4px 12px rgba(217,22,36,.22);
}
.hero-board span, .metric span, .trade-strip span, .day-card span, .agent-card span { color: #667484; }
.hero-board strong, .trade-strip strong { color: #121a23; }
.metric {
  min-height: 118px;
  padding: 18px;
}
.metric i {
  border-color: rgba(47,95,181,.20);
  box-shadow: inset 0 0 14px rgba(47,95,181,.08);
}
.metric strong {
  color: #b20b15;
  font-size: 30px;
  text-shadow: none;
}
.equity-panel svg {
  border-radius: 8px;
  background:
    linear-gradient(#e9eef4 1px, transparent 1px),
    linear-gradient(90deg, #e9eef4 1px, transparent 1px),
    #fbfcfe;
  background-size: 34px 34px;
}
.days-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.day-card {
  min-height: 214px;
  padding: 20px;
  background: #fff;
}
.day-card:hover {
  border-color: #c20d17;
  box-shadow: 0 18px 38px rgba(194, 13, 23, .16);
}
.day-card strong {
  color: #b20b15;
  text-shadow: none;
}
.day-card::after {
  border-color: rgba(47,95,181,.10);
}
.ticker-cloud span, .rank-chip, .risk {
  color: #1a2a3a;
  background: #eef2f6;
  border-color: #dbe3eb;
  box-shadow: none;
}
.mission-panel {
  background: rgba(255,255,255,.64);
  border-color: #d6dee7;
}
.mission-panel > span { color: #667484; }
.mini-nav a {
  color: #1f5da7;
  background: #eef5fc;
  border-color: #d7e3f0;
  box-shadow: none;
}
th { color: #647183; background: #f2f5f8; }
td { color: #17212c; }
tr:hover td { background: #f7f9fb; }
.pos { color: #087c32; text-shadow: none; }
.neg { color: #c20d17; text-shadow: none; }
.stock-panel {
  border-radius: 12px;
}
.stock-head {
  grid-template-columns: 1fr 140px 118px;
  padding: 24px;
  background:
    linear-gradient(180deg, #ffffff, #f6f8fa),
    none;
}
.signal-stack {
  background: #f2f5f8;
  border-color: #dce4ec;
}
.signal-stack span { color: #697789; }
.signal-stack b { color: #b20b15; }
.score-orb {
  width: 106px;
  height: 106px;
  background: #fff;
  border-color: #d91624;
  box-shadow: 0 14px 28px rgba(194,13,23,.16), inset 0 0 0 8px #f5f7fa;
}
.score-orb strong { color: #b20b15; }
.score-orb span { color: #667484; }
.meter { background: #e9eef4; box-shadow: none; }
.meter i { box-shadow: none; }
.score-row { color: #283746; }
dt { color: #667484; }
dd { color: #17212c; }
.agent-card {
  border-color: #dce3eb;
  background: #f9fbfd;
}
.agent-card p { color: #344354; }
ul { color: #344354; }
.muted { color: #7b8794; }
@media (max-width: 900px) {
  .app-frame { grid-template-columns: 1fr; }
  .side-nav { position: relative; height: auto; display: flex; gap: 8px; overflow-x: auto; border-right: 0; border-bottom: 1px solid #dbe2ea; }
  .brand-mark { min-width: 170px; margin-bottom: 0; }
  .side-nav a { white-space: nowrap; }
  .days-grid { grid-template-columns: 1fr; }
}
"""
    (output_dir / "style.css").write_text(css, encoding="utf-8")


def inline_css(output_dir: Path) -> None:
    """Embed CSS into every page so single-file previews keep the visual design."""
    css_path = output_dir / "style.css"
    css = css_path.read_text(encoding="utf-8")
    inline = f"<style>\n{css}\n</style>"
    link = '<link rel="stylesheet" href="style.css">'
    for path in output_dir.glob("*.html"):
        text = path.read_text(encoding="utf-8")
        if link in text:
            text = text.replace(link, inline)
            path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    analysis_dir = Path(args.analysis_dir)
    portfolio_dir = Path(args.portfolio_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.html", "style.css", "manifest.json"):
        for path in output_dir.glob(pattern):
            path.unlink()

    payloads = load_analysis(analysis_dir)
    if not payloads:
        raise FileNotFoundError(f"analysis json not found: {analysis_dir}")

    summary_path = portfolio_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    trades = read_csv(portfolio_dir / "trades.csv")
    skipped = read_csv(portfolio_dir / "skipped_entries.csv")
    equity = read_csv(portfolio_dir / "equity_curve.csv")
    selection_records = read_csv(portfolio_dir / "selection_records.csv")

    write_css(output_dir)
    index_page(payloads, output_dir, summary, equity, args.title)
    for payload in payloads:
        date_page(payload, output_dir, trades, skipped, selection_records, args.title)
    inline_css(output_dir)

    manifest = {
        "analysis_dir": str(analysis_dir),
        "portfolio_dir": str(portfolio_dir),
        "output_dir": str(output_dir),
        "pages": ["index.html", *[f"{p['date']}.html" for p in payloads]],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {output_dir / 'index.html'}")
    print(f"pages={','.join(manifest['pages'])}")


if __name__ == "__main__":
    main()
