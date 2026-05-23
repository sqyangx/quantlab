# QuantLab

[English](README.md) | 中文

A 股 T+1 量化交易系统，融合三个微软开源项目，构建从数据到交易的完整日频管线。

> 最新项目架构图：[网页预览](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/project_architecture.html)（[源码](docs/project_architecture.html)）

| 组件 | 角色 |
|------|------|
| [Qlib](https://github.com/microsoft/qlib) | 数据基础设施、Alpha158 因子引擎、回测框架 |
| [Kronos](https://github.com/shiyu-coder/Kronos) | K 线序列预测 Transformer 基础模型 |
| [RD-Agent](https://github.com/microsoft/RD-Agent) | LLM 驱动的进化式因子/模型自动发现 |

## 最新特性

- **Agentic 复核层**：`quantlab.agentic` 提供独立的候选股票复核模块，支持流动性检查、板块资金流暴露、行业集中度检查，以及 `approve/reduce/veto/review` 结构化决策。
- **板块资金流数据层**：`quantlab.data.sector_flow_*` 支持板块资金流下载、标准化、交易日历对齐和滚动特征生成，可与现有 Qlib 日频数据和行业映射对齐。
- **新特性介绍文章**：[Agentic 新特性文章](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/agentic_feature_article.html) 详细说明复核层、板块资金流对齐、日频决策流程和实验路线。
- **项目架构 HTML**：[网页预览](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/project_architecture.html) 展示数据、信号、融合选股、Agentic 复核、执行、风控、评估和运维的完整链路。源码文件位于 [docs/project_architecture.html](docs/project_architecture.html)。

## 系统架构

完整的新设计请优先查看：[网页预览版](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/project_architecture.html)。GitHub 普通 `blob` 页面默认展示 HTML 源码，这是平台行为。

```
  T 日收盘触发
      │
      ▼
┌─────────────────────────────────────────────┐
│           数据层（Qlib）                      │
│  OHLCV + Alpha158 因子 + 交易日历             │
│  严格时间隔离：所有数据 ≤ T 日                 │
└─────┬──────────────┬──────────────┬─────────┘
      │              │              │
      ▼              ▼              ▼
┌──────────┐  ┌────────────┐  ┌────────────┐
│ Alpha158 │  │   Kronos   │  │  RD-Agent  │
│+LightGBM │  │ 5日K线预测  │  │  进化因子   │
│ 趋势/动量 │  │ +不确定性   │  │  均值回复   │
└────┬─────┘  └─────┬──────┘  └─────┬──────┘
     │              │               │
     └──────────────┼───────────────┘
                    ▼
         ┌──────────────────┐
         │    信号融合        │
         │  IC加权 + 排序归一 │
         └────────┬─────────┘
                  ▼
         ┌──────────────────┐
         │   T+1 交易执行    │
         │   开盘价成交      │
         └────────┬─────────┘
                  ▼
         ┌──────────────────┐
         │    风险控制        │
         │   三级风控体系     │
         └────────┬─────────┘
                  ▼
         ┌──────────────────┐
         │    绩效评估        │
         │ Sharpe / IC / 归因│
         └──────────────────┘
```

**核心设计原则：** 所有数据查询强制 `anchor_date` 约束 — 任何模块都不能访问 T 日之后的数据，杜绝前视偏差。

## 模块总览

| 模块 | 路径 | 说明 |
|------|------|------|
| M1 数据管理 | `data/data_manager.py` | 数据更新（Yahoo/Baostock/CSV → Qlib bin）+ 时间隔离访问 |
| M1.5 数据可视化 | `data/data_viewer.py` | CSV 导出、K 线图（Plotly）、持仓概览 |
| M2 Alpha 信号 | `signal/signal_alpha.py` | Alpha158 + LightGBM（日频趋势/动量信号） |
| M3 Kronos 信号 | `signal/signal_kronos.py` | Kronos 5 日预测（K 线形态信号） |
| M4 RD-Agent 信号 | `signal/signal_rdagent.py`, `signal/factor_spec.py` | RD-Agent 进化因子与确定性 factor-spec 编译 |
| M5 信号融合 | `signal/signal_ensemble.py` | 排序归一化 + 扩展窗口 IC 加权 |
| M6 交易执行 | `execution/execution.py` | T+1 开盘价交易执行 |
| M7 风险控制 | `risk_control/risk_control.py` | 个股止损、行业上限、组合熔断 |
| M8 绩效评估 | `evaluation/evaluation.py` | Sharpe、IC 衰减、收益归因 |
| M9 回测调度 | `main.py` | 日频回测调度器（支持断点续跑） |
| Agentic 复核 | `agentic/` | 独立候选股票复核层，输出风险发现、否决/降权/通过决策和复核记录 |
| 板块资金流 | `data/sector_flow_*.py` | 板块资金流下载、标准化、交易日历对齐和滚动特征 |

## 快速开始

### 环境要求

- Python 3.10 或 3.11（推荐）
- C++ 编译器（Qlib 含 Cython 扩展需要编译）
  - **Windows:** 安装 [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)，勾选「C++ 生成工具」
  - **Linux:** `sudo apt install build-essential`
  - **macOS:** `xcode-select --install`

### 安装步骤

```bash
# 克隆仓库（含子模块）
git clone --recursive https://github.com/sqyangx/quantlab.git
cd quantlab

# 创建 conda 虚拟环境
conda create -n quantlab python=3.11 -y
conda activate quantlab

# 安装 Qlib（本地源码，会触发 Cython 编译）
pip install -e ./qlib

# 安装 QuantLab
pip install -e .

# 验证环境 + 下载 A 股数据（约 200-500MB）
python quantlab/setup_and_verify.py
```

### 运行回测

```bash
# 完整回测
python quantlab/main.py --config quantlab/configs/backtest.yaml

# 从断点恢复
python quantlab/main.py --resume checkpoints/checkpoint_2024-06-28.pkl
```

### 运行测试

```bash
python -m pytest quantlab/tests/ -v
```

## 配置说明

主配置文件：`quantlab/configs/backtest.yaml`

```yaml
# 回测区间
start_date: "2023-01-01"
end_date: "2025-03-01"

# 市场配置
market: "csi300"               # 沪深300股票池
initial_cash: 1000000          # 初始资金 100万

# 管线开关
enable_alpha: true             # Alpha158 + LightGBM
enable_kronos: true            # Kronos Transformer
enable_rdagent: false          # RD-Agent（需要 LLM API，默认关闭）

# 交易执行
max_positions: 10              # 最大持仓数
max_single_weight: 0.20       # 单只股票最大仓位 20%

# 风险控制
stop_loss_pct: 0.08            # 个股止损线 8%
max_industry_pct: 0.30         # 单行业上限 30%
circuit_breaker_pct: 0.10      # 组合熔断线 10%
```

完整参数详见 [backtest.yaml](quantlab/configs/backtest.yaml)。

## 交易逻辑

### T+1 交易周期

1. **T 日收盘** — 获取截至 T 日的全部历史数据
2. **信号生成** — 三条管线各自产出独立信号：
   - **Alpha158**：158 个技术因子 + LightGBM，每 20 个交易日滚动重训
   - **Kronos**：Transformer 预测未来 5 日 OHLCV，10 次采样估计不确定性
   - **RD-Agent**：LLM 进化因子，每周迭代一轮（可选）
3. **信号融合** — 各信号排序归一化，按扩展窗口 IC 相关性动态加权
4. **订单生成** — 选取头部/尾部股票，考虑仓位限制
5. **T+1 日开盘** — 以开盘价执行（买入仅在开盘价 ≤ 目标价时成交）
6. **风控检查** — 止损/行业上限/熔断全程监控

### 三级风控

| 级别 | 触发条件 | 动作 |
|------|----------|------|
| 个股止损 | 持仓回撤 ≥ 8%（相对最高价） | 强制卖出 |
| 行业上限 | 单行业敞口 > 组合 30% | 削减仓位 |
| 组合熔断 | 净值回撤 ≥ 10%（相对高水位） | 暂停交易 5 天 |

## 项目结构

```
quantlab/
├── configs/                    # YAML 配置文件
│   ├── backtest.yaml           # 主回测配置
│   ├── kronos_recipes.yaml     # Kronos 模型配方
│   └── rdagent_evolution.yaml  # RD-Agent 进化设置
├── agentic/                    # Agentic 候选股票复核层
├── data/                       # M1 & M1.5：数据层
├── signal/                     # M2-M5：信号管线
├── execution/                  # M6：交易执行
├── risk_control/               # M7：风险管理
├── evaluation/                 # M8：绩效分析
├── tests/                      # 测试套件
├── main.py                     # M9：回测调度器
└── setup_and_verify.py         # 环境初始化
```

## 文档

- [Agentic 新特性介绍文章](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/agentic_feature_article.html) — 详细介绍 Agentic 复核层和板块资金流特性（[源码](docs/agentic_feature_article.html)）
- [Factor-Spec Pipeline](docs/factor_spec_pipeline.md) — RD-Agent 风格因子搜索的结构化规格、确定性编译和采样冒烟测试流程
- [项目架构图网页预览](https://htmlpreview.github.io/?https://github.com/sqyangx/quantlab/blob/main/docs/project_architecture.html) — 当前项目架构图和 Agentic/板块资金流新设计（[源码](docs/project_architecture.html)）
- [DESIGN.md](DESIGN.md) — 系统架构概要设计
- [DETAIL_DESIGN.md](DETAIL_DESIGN.md) — 模块详细设计（M1-M9）
- [docs/](docs/) — 各模块使用文档

## 致谢

本项目基于微软的三个优秀开源项目构建：

- [Qlib](https://github.com/microsoft/qlib) — AI 量化投资平台
- [Kronos](https://github.com/shiyu-coder/Kronos) — 预训练时序预测模型
- [RD-Agent](https://github.com/microsoft/RD-Agent) — LLM 驱动的研发智能体

## 许可证

[MIT](LICENSE)
