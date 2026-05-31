# TradingAgents Post Analysis

这是一个独立的选股后处理分析模块，不依赖 Kronos 实验脚本，也不依赖 Model-A 训练代码。

## 输入

候选池 CSV 或 DataFrame，至少包含：

- `ticker`: 股票代码，例如 `SH600000`、`SZ000001`

建议包含：

- `candidate_rank`: 上游候选排序
- `model_a_score`: 上游模型分数
- `pred_endpoint`: Kronos 端点收益特征
- `uncertainty`: 不确定性特征
- `path_max_dd_mean`: 路径回撤特征

## 输出

每个交易日输出：

- `{date}_analysis.json`: 完整结构化分析结果
- `{date}_ranked.csv`: 二次排序表
- `{date}_REPORT.md`: 简版报告

## 命令行

```bash
/home/gpu/.conda/envs/asrlab/bin/python -m quantlab.post_analysis.tradingagents \
  --candidates-csv /path/to/candidates.csv \
  --date 2026-05-25 \
  --output-dir /path/to/output \
  --data-dir quantlab/02_data_5min/min_data \
  --industry-map quantlab/industry_map.csv
```

加上 `--fetch-external` 后会真实请求财报、公告、新闻数据；默认只使用缓存或记录缺失状态，避免发布环境误触外部请求。

## 模块边界

上游实验只负责生成候选池。该模块只负责：

- 读取 5min 技术证据
- 拉取或读取外部财报、公告、新闻
- 构建标题情绪分
- 生成多智能体分析意见
- 对候选池二次排序并输出 topN

## 大模型分析接入

`llm_prompts.py` 提供 `build_stock_analysis_messages(candidate)`，用于把单只候选股的结构化证据转成中文大模型消息。当前模块不绑定任何具体 LLM provider，发布环境可以接 OpenAI-compatible、本地模型或内部模型客户端。

分析维度固定为：

- 形态与盘面
- 量化信号
- 基本面
- 事件与情绪
- 多方博弈
- 交易复盘

要求大模型输出普通人能读懂的中文结论，不能直接复述 HTML 标题或原始新闻噪声；没有获取到的财务、公告、新闻或后续行情必须明确标注为缺失。
