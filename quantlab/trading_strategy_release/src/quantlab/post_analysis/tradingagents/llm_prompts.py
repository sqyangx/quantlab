"""LLM prompt builders for post-selection stock analysis.

The module intentionally does not bind to a specific LLM provider. Production
code can pass the returned messages to OpenAI-compatible, local, or internal
model clients.
"""

from __future__ import annotations

import json
from typing import Any


ANALYSIS_DIMENSIONS = (
    "形态与盘面：解释日内趋势、最后一小时变化、成交额和波动风险。",
    "量化信号：解释 Model-A 排名、分数、Kronos 端点收益和不确定性。",
    "基本面：解释行业、ROE、毛利率、净利润等财务线索，缺失时明确说明。",
    "事件与情绪：把公告、新闻、舆情命中转写成普通投资者能理解的语言。",
    "多方博弈：分别给出看多、看空、风控和交易员观点，最后形成一致结论。",
    "交易复盘：如已有后续行情，说明买入时间/价格、卖出时间/价格和实际收益。",
)


def compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Keep prompt input focused and stable across upstream experiment versions."""
    allowed = {
        "date",
        "ticker",
        "name",
        "industry",
        "candidate_rank",
        "model_a_score",
        "final_score",
        "risk_level",
        "decision",
        "quant_score",
        "technical_score",
        "fundamental_score",
        "event_sentiment_score",
        "bear_risk_score",
        "technical",
        "financial",
        "sentiment",
        "announcements",
        "news",
        "agent_report",
        "realized_trade",
        "realized_return",
    }
    return {key: candidate.get(key) for key in allowed if key in candidate}


def build_stock_analysis_messages(candidate: dict[str, Any]) -> list[dict[str, str]]:
    """Build Chinese LLM messages for one selected stock."""
    payload = compact_candidate(candidate)
    system = (
        "你是一个A股量化投研多智能体协调器。你的任务不是复述原始新闻标题，"
        "而是把量化信号、形态、基本面、公告新闻和真实交易结果转成可读的中文投研结论。"
        "不要编造不存在的数据；缺失的数据必须明确写成未获取。"
    )
    user = {
        "任务": "对单只股票生成最终推荐/不推荐理由，并给出多智能体讨论摘要。",
        "分析维度": list(ANALYSIS_DIMENSIONS),
        "输出格式": {
            "一句话结论": "是否建议进入最终5只组合，以及核心原因。",
            "形态分析": "用普通语言解释价格和成交行为。",
            "基本面分析": "解释财务和行业线索，缺失则说明。",
            "事件分析": "把公告、新闻、情绪数据翻译成人话，过滤HTML和噪声。",
            "多智能体讨论": {
                "看多方": "支持买入的证据。",
                "看空方": "主要风险和反对理由。",
                "风控方": "仓位、T+1、资金占用和退出条件。",
                "交易员": "最终执行建议。",
            },
            "交易复盘": "如有后续数据，列出买入/卖出时间、价格和收益；没有则写待观察。",
        },
        "候选数据": payload,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False, indent=2)},
    ]

