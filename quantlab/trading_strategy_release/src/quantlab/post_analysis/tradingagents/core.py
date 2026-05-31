"""TradingAgents-style post-selection reranking core.

The core accepts a candidate DataFrame and does not import experiment modules.
Repository-specific adapters can prepare Model-A top20 candidates separately.
"""

from __future__ import annotations

import html
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests


FIELDS = ("open", "high", "low", "close", "volume", "amount")
POSITIVE_WORDS = ("增长", "预增", "盈利", "中标", "订单", "回购", "增持", "突破", "创新高", "改善", "扩产", "合作")
NEGATIVE_WORDS = ("亏损", "预亏", "减持", "处罚", "问询", "诉讼", "退市", "下滑", "风险", "冻结", "违约", "终止")


@dataclass
class ExternalEvidence:
    ticker: str
    name: str = ""
    financial: dict[str, Any] | None = None
    announcements: list[dict[str, Any]] | None = None
    news: list[dict[str, Any]] | None = None
    sentiment: dict[str, Any] | None = None
    errors: list[str] | None = None


def qlib_to_code(ticker: str) -> str:
    return ticker.upper().replace("SH", "").replace("SZ", "")


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def summarize_event_titles(ann_titles: list[str], news_titles: list[str]) -> str:
    titles = [clean_text(x) for x in [*ann_titles, *news_titles] if clean_text(x)]
    if not titles:
        return "暂未抓到可用公告或新闻，事件面不作为加分项。"
    joined = "；".join(titles[:6])
    themes: list[str] = []
    if "龙虎榜" in joined:
        themes.append("短线资金关注度较高，需结合成交额确认是否只是游资博弈")
    if "异常波动" in joined:
        themes.append("存在股票交易异常波动提示，追涨风险需要单独扣分")
    if "股东会" in joined:
        themes.append("有股东会或治理相关公告，偏信息披露线索，不直接等同业绩改善")
    if any(word in joined for word in ("减持", "处罚", "问询", "诉讼", "退市", "风险")):
        themes.append("标题中出现风险或监管类关键词，建议降低仓位权重")
    if any(word in joined for word in ("中标", "订单", "合作", "增持", "回购")):
        themes.append("标题中出现订单、合作或股东增持回购线索，可作为事件催化观察")
    if not themes:
        themes.append("公告和新闻以常规信息披露为主，暂未形成明确事件催化")
    return "；".join(themes) + "。"


def baostock_code(ticker: str) -> str:
    ticker = ticker.upper()
    if ticker.startswith("SH"):
        return "sh." + ticker[2:]
    if ticker.startswith("SZ"):
        return "sz." + ticker[2:]
    raise ValueError(f"unsupported ticker: {ticker}")


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


def load_symbol_frame(data_dir: Path, calendar: pd.DatetimeIndex, symbol: str) -> pd.DataFrame:
    feature_dir = data_dir / "features" / symbol.lower()
    arrays = {}
    for field in FIELDS:
        path = feature_dir / f"{field}.5min.bin"
        arrays[field] = read_field_bin(path, len(calendar)) if path.exists() else np.full(len(calendar), np.nan)
    return pd.DataFrame(arrays, index=calendar)


def intraday_features(df: pd.DataFrame, date: str) -> dict[str, Any]:
    anchor = pd.Timestamp(f"{date} 15:00:00")
    day = df.loc[(df.index.date == anchor.date()) & (df.index <= anchor)].dropna(subset=["open", "close"], how="any")
    if day.empty:
        return {"day_return": None, "last_hour_return": None, "amplitude": None, "amount": None}
    first_open = float(day.iloc[0]["open"])
    last_close = float(day.iloc[-1]["close"])
    high = float(day["high"].max())
    low = float(day["low"].min())
    last_hour_ts = pd.Timestamp(f"{date} 14:00:00")
    last_hour = last_close / float(day.loc[last_hour_ts, "close"]) - 1.0 if last_hour_ts in day.index else np.nan
    return {
        "day_return": last_close / first_open - 1.0 if first_open > 0 else None,
        "last_hour_return": float(last_hour) if np.isfinite(last_hour) else None,
        "amplitude": high / low - 1.0 if low > 0 else None,
        "amount": float(day["amount"].sum()) if "amount" in day else None,
    }


def load_industry_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    return dict(zip(df["symbol"].astype(str).str.upper(), df["industry"].astype(str)))


def cache_json(cache_dir: Path, group: str, ticker: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    path = cache_dir / group / f"{ticker}.json"
    if payload is None:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def request_json(url: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    session = requests.Session()
    session.trust_env = False
    resp = session.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    text = resp.text.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    elif "(" in text and text.endswith(")"):
        text = re.sub(r"^[^(]*\(", "", text)[:-1]
    return json.loads(text)


def report_period_candidates(signal_date: str) -> list[tuple[int, int]]:
    ts = pd.Timestamp(signal_date)
    year = int(ts.year)
    month = int(ts.month)
    candidates: list[tuple[int, int]] = []
    if month >= 11:
        candidates.append((year, 3))
    if month >= 9:
        candidates.append((year, 2))
    if month >= 5:
        candidates.append((year, 1))
    candidates.extend([(year - 1, 4), (year - 1, 3), (year - 1, 2), (year - 1, 1)])
    out = []
    seen = set()
    for item in candidates:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def fetch_baostock_financial(ticker: str, signal_date: str) -> dict[str, Any]:
    import baostock as bs

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock login failed: {lg.error_code} {lg.error_msg}")
    try:
        for year, quarter in report_period_candidates(signal_date):
            rs = bs.query_profit_data(code=baostock_code(ticker), year=year, quarter=quarter)
            if rs.error_code != "0" or not rs.next():
                continue
            row = dict(zip(rs.fields, rs.get_row_data()))
            row.update(
                {
                    "source": "baostock_query_profit_data",
                    "report_year": year,
                    "report_quarter": quarter,
                    "roe": row.get("roeAvg"),
                    "gross_margin": row.get("gpMargin"),
                    "net_profit": row.get("netProfit"),
                    "eps_ttm": row.get("epsTTM"),
                }
            )
            return row
        return {"source": "baostock_query_profit_data", "missing": "no_profit_data"}
    finally:
        bs.logout()


def fetch_announcements(ticker: str, timeout: float) -> list[dict[str, Any]]:
    raw = request_json(
        "https://np-anotice-stock.eastmoney.com/api/security/ann",
        {
            "sr": "-1",
            "page_size": "8",
            "page_index": "1",
            "ann_type": "A",
            "client_source": "web",
            "stock_list": qlib_to_code(ticker),
        },
        timeout,
    )
    items = raw.get("data", {}).get("list") or []
    return [
        {
            "title": item.get("title"),
            "date": item.get("notice_date") or item.get("display_time"),
            "columns": item.get("columns"),
            "source": "eastmoney_announcement",
        }
        for item in items[:8]
    ]


def fetch_news(ticker: str, timeout: float) -> list[dict[str, Any]]:
    cb = "jQuery3510875346244069884_1668256937995"
    raw = request_json(
        "https://search-api-web.eastmoney.com/search/jsonp",
        {
            "cb": cb,
            "param": json.dumps(
                {
                    "uid": "",
                    "keyword": qlib_to_code(ticker),
                    "type": ["cmsArticleWebOld"],
                    "client": "web",
                    "clientType": "web",
                    "clientVersion": "curr",
                    "param": {
                        "cmsArticleWebOld": {
                            "searchScope": "default",
                            "sort": "default",
                            "pageIndex": 1,
                            "pageSize": 8,
                            "preTag": "",
                            "postTag": "",
                        }
                    },
                },
                ensure_ascii=False,
            ),
            "_": str(int(time.time() * 1000)),
        },
        timeout,
    )
    result = raw.get("result") or {}
    items = result.get("cmsArticleWebOld") or result.get("items") or []
    return [
        {
            "title": clean_text(item.get("title") or item.get("Title")),
            "content": clean_text(item.get("content")),
            "date": item.get("date") or item.get("showTime") or item.get("publishTime"),
            "source": item.get("mediaName") or item.get("source") or "eastmoney_search",
            "url": item.get("url"),
        }
        for item in items[:8]
    ]


def build_sentiment(news: list[dict[str, Any]], announcements: list[dict[str, Any]]) -> dict[str, Any]:
    texts = [str(x.get("title") or "") for x in [*news, *announcements]]
    pos = sum(any(word in text for word in POSITIVE_WORDS) for text in texts)
    neg = sum(any(word in text for word in NEGATIVE_WORDS) for text in texts)
    total = max(1, len(texts))
    return {
        "score": (pos - neg) / total,
        "positive_hits": pos,
        "negative_hits": neg,
        "sample_count": len(texts),
        "method": "title_keyword_lexicon",
    }


def get_external_evidence(
    ticker: str,
    signal_date: str,
    cache_dir: Path,
    fetch: bool,
    timeout: float,
    sleep_seconds: float,
) -> ExternalEvidence:
    cached = cache_json(cache_dir, "evidence", ticker)
    if cached and not fetch:
        return ExternalEvidence(**cached)
    evidence = ExternalEvidence(ticker=ticker, financial={}, announcements=[], news=[], sentiment={}, errors=[])
    if not fetch:
        evidence.errors.append("external_fetch_disabled")
        cache_json(cache_dir, "evidence", ticker, evidence.__dict__)
        return evidence
    for label in ("financial", "announcements", "news"):
        try:
            if label == "financial":
                value = fetch_baostock_financial(ticker, signal_date)
            elif label == "announcements":
                value = fetch_announcements(ticker, timeout)
            else:
                value = fetch_news(ticker, timeout)
            setattr(evidence, label, value)
            time.sleep(sleep_seconds)
        except Exception as exc:  # noqa: BLE001
            evidence.errors.append(f"{label}: {type(exc).__name__}: {exc}")
    evidence.sentiment = build_sentiment(evidence.news or [], evidence.announcements or [])
    cache_json(cache_dir, "evidence", ticker, evidence.__dict__)
    return evidence


def finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return out


def normalize_score(value: float | None, low: float, high: float, inverse: bool = False) -> float:
    if value is None or high <= low:
        return 0.0
    score = max(0.0, min(1.0, (value - low) / (high - low)))
    return 1.0 - score if inverse else score


def percent_like(value: Any) -> float | None:
    number = finite_float(value)
    if number is None:
        return None
    return number * 100.0 if abs(number) <= 1.0 else number


def analyst_scores(row: pd.Series, industry: str, tech: dict[str, Any], ev: ExternalEvidence) -> dict[str, Any]:
    fin = ev.financial or {}
    sentiment = ev.sentiment or {}
    roe = percent_like(fin.get("roe"))
    gross_margin = percent_like(fin.get("gross_margin"))
    model_rank = int(row["candidate_rank"])
    model_score = finite_float(row.get("model_a_score")) or 0.0
    uncertainty = finite_float(row.get("uncertainty"))
    endpoint = finite_float(row.get("pred_endpoint"))
    path_dd = finite_float(row.get("path_max_dd_mean"))
    amount = finite_float(tech.get("amount"))

    quant = 0.55 * (1.0 - (model_rank - 1) / 20.0)
    quant += 0.25 * normalize_score(model_score, 0.0, 2.0)
    quant += 0.20 * normalize_score(endpoint, -0.03, 0.03)

    technical = 0.35 * normalize_score(tech.get("day_return"), -0.08, 0.08)
    technical += 0.25 * normalize_score(tech.get("last_hour_return"), -0.04, 0.04)
    technical += 0.25 * normalize_score(amount, 2e7, 1e9)
    technical += 0.15 * normalize_score(path_dd, -0.08, 0.0)

    fundamental_parts = []
    if roe is not None:
        fundamental_parts.append(normalize_score(roe, -20, 30))
    if gross_margin is not None:
        fundamental_parts.append(normalize_score(gross_margin, 0, 60))
    fundamental = float(np.mean(fundamental_parts)) if fundamental_parts else 0.5

    event_sentiment = normalize_score(finite_float(sentiment.get("score")), -1.0, 1.0)
    risk_penalty = 0.0
    risk_penalty += 0.20 * normalize_score(uncertainty, 0.0, 0.03)
    risk_penalty += 0.15 * normalize_score(tech.get("amplitude"), 0.0, 0.16)
    risk_penalty += 0.15 * max(0.0, -(finite_float(sentiment.get("score")) or 0.0))

    bear = min(1.0, risk_penalty + 0.20 * (1.0 - fundamental) + 0.10 * max(0.0, -normalize_score(endpoint, -0.03, 0.03)))
    final = 0.36 * quant + 0.24 * technical + 0.20 * fundamental + 0.12 * event_sentiment - 0.20 * bear
    final = max(0.0, min(1.0, final))

    return {
        "quant_score": quant,
        "technical_score": technical,
        "fundamental_score": fundamental,
        "event_sentiment_score": event_sentiment,
        "bear_risk_score": bear,
        "final_score": final,
        "decision": "建议纳入top5" if final >= 0.55 else "候补观察",
        "risk_level": "高" if bear >= 0.55 else ("中" if bear >= 0.35 else "低"),
        "industry": industry,
    }


def text_or_unknown(value: Any) -> str:
    if value is None or value == "" or (isinstance(value, float) and not math.isfinite(value)):
        return "暂无"
    return str(value)


def pct_or_unknown(value: Any) -> str:
    number = finite_float(value)
    if number is None:
        return "暂无"
    return f"{number:.2%}"


def amount_or_unknown(value: Any) -> str:
    number = finite_float(value)
    if number is None:
        return "暂无"
    return f"{number / 1e8:.2f}亿元"


def build_agent_report(row: pd.Series, tech: dict[str, Any], ev: ExternalEvidence, scores: dict[str, Any]) -> dict[str, str]:
    fin = ev.financial or {}
    sentiment = ev.sentiment or {}
    ann_titles = [clean_text(x.get("title")) for x in (ev.announcements or []) if x.get("title")]
    news_titles = [clean_text(x.get("title")) for x in (ev.news or []) if x.get("title")]
    missing = "；".join(ev.errors or []) if ev.errors else "外部证据已缓存"
    return {
        "量化证据分析师": (
            f"Model-A 候选排序第 {int(row['candidate_rank'])}，分数 {float(row['model_a_score']):.6f}。"
            f"Kronos endpoint={float(row.get('pred_endpoint', 0)):.4%}，不确定性={float(row.get('uncertainty', 0)):.6f}。"
            f"量化分 {scores['quant_score']:.3f}。"
        ),
        "技术分析师": (
            f"15:00 前日内涨跌 {pct_or_unknown(tech.get('day_return'))}，"
            f"最后一小时 {pct_or_unknown(tech.get('last_hour_return'))}，"
            f"成交额 {amount_or_unknown(tech.get('amount'))}。技术分 {scores['technical_score']:.3f}。"
        ),
        "基本面分析师": (
            f"行业为 {scores['industry']}。ROE={text_or_unknown(fin.get('roe'))}，"
            f"毛利率={text_or_unknown(fin.get('gross_margin'))}，净利润={text_or_unknown(fin.get('net_profit'))}。"
            f"基本面分 {scores['fundamental_score']:.3f}。"
        ),
        "事件解读分析师": (
            f"公告 {len(ann_titles)} 条、新闻 {len(news_titles)} 条；"
            f"正向命中 {sentiment.get('positive_hits', 0)}、负向命中 {sentiment.get('negative_hits', 0)}，"
            f"事件分 {scores['event_sentiment_score']:.3f}。"
            f"{summarize_event_titles(ann_titles, news_titles)}"
        ),
        "看多研究员": "看多理由：候选排名靠前、短线模型分较高；若技术分和公告/新闻情绪同时为正，可作为 top20 中优先候选。",
        "看空研究员": (
            f"反方观点：外部证据缺失或负面标题会降低可信度；高不确定性、振幅过大和基本面弱会抬升风险。"
            f"风险分 {scores['bear_risk_score']:.3f}。"
        ),
        "交易员结论": (
            f"{scores['decision']}，最终分 {scores['final_score']:.3f}，风险等级 {scores['risk_level']}。"
            "该结论只用于 Model-A top20 后的二次排序，不改变前置候选流程。"
        ),
        "数据状态": missing,
    }


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if not isinstance(obj, (list, dict, str, tuple)):
        try:
            if pd.isna(obj):
                return None
        except Exception:
            pass
    return obj


def run_analysis(
    candidates: pd.DataFrame,
    date: str,
    output_dir: Path,
    data_dir: Path | None = None,
    industry_map_path: Path | None = None,
    cache_dir: Path = Path(".cache/tradingagents_external_cache"),
    final_n: int = 5,
    fetch_external: bool = False,
    request_timeout: float = 8.0,
    sleep_seconds: float = 0.2,
) -> dict[str, Any]:
    """Run post-selection analysis on an existing candidate pool."""
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = candidates.copy()
    candidates["ticker"] = candidates["ticker"].astype(str).str.upper()
    if "candidate_rank" not in candidates.columns:
        candidates["candidate_rank"] = np.arange(1, len(candidates) + 1)

    industries = load_industry_map(industry_map_path) if industry_map_path else {}
    calendar = read_calendar(data_dir / "calendars" / "5min.txt") if data_dir else None
    rows = []
    for _, row in candidates.iterrows():
        ticker = str(row["ticker"]).upper()
        if data_dir and calendar is not None:
            tech = intraday_features(load_symbol_frame(data_dir, calendar, ticker), date)
        else:
            tech = {"day_return": None, "last_hour_return": None, "amplitude": None, "amount": None}
        evidence = get_external_evidence(ticker, date, cache_dir, fetch_external, request_timeout, sleep_seconds)
        scores = analyst_scores(row, industries.get(ticker, "未知行业"), tech, evidence)
        rows.append(
            {
                "date": date,
                "ticker": ticker,
                "name": evidence.name,
                "candidate_rank": int(row["candidate_rank"]),
                "model_a_score": float(row.get("model_a_score", np.nan)),
                "scores": scores,
                "technical_features": tech,
                "external_evidence": evidence.__dict__,
                "agent_report": build_agent_report(row, tech, evidence, scores),
            }
        )

    ranked = sorted(rows, key=lambda x: x["scores"]["final_score"], reverse=True)
    payload = {
        "date": date,
        "candidate_n": int(len(candidates)),
        "final_n": int(final_n),
        "selection_stage": "upstream candidate pool unchanged",
        "rerank_stage": "TradingAgents analyst module with financial/announcement/news/sentiment evidence",
        "fetch_external": bool(fetch_external),
        "final_tickers": [x["ticker"] for x in ranked[:final_n]],
        "candidates": ranked,
    }
    (output_dir / f"{date}_analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=to_jsonable),
        encoding="utf-8",
    )
    table = pd.DataFrame(
        [
            {
                "date": date,
                "final_rank": i + 1,
                "ticker": item["ticker"],
                "name": item["name"],
                "model_a_rank": item["candidate_rank"],
                "model_a_score": item["model_a_score"],
                **item["scores"],
            }
            for i, item in enumerate(ranked)
        ]
    )
    table.to_csv(output_dir / f"{date}_ranked.csv", index=False)
    (output_dir / f"{date}_REPORT.md").write_text(build_report_markdown(date, len(candidates), final_n, fetch_external, table), encoding="utf-8")
    return payload


def build_report_markdown(date: str, candidate_n: int, final_n: int, fetch_external: bool, table: pd.DataFrame) -> str:
    lines = [
        f"# {date} TradingAgents 二级分析",
        "",
        f"- 前置候选：top{candidate_n}",
        f"- 最终建议：top{final_n}",
        f"- 外部数据请求：`{fetch_external}`",
        "",
        "## 建议 Top5",
        "",
        table.head(final_n).to_markdown(index=False, floatfmt=".6f"),
        "",
        "## 说明",
        "",
        "本模块是选股后的二级分析层；不得替代前置候选生成，也不得在外部证据缺失时编造财报、公告、新闻或情绪事实。",
    ]
    return "\n".join(lines) + "\n"
