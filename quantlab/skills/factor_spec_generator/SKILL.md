# QuantLab Factor Spec Generator Skill

Purpose: generate offline factor specifications for QuantLab without requiring API-based RD-Agent runs. Use this skill when the task is to design, debate, review, or produce structured `factor_spec` candidates that will later be compiled into deterministic code.

This skill can run inside one Codex session. It does not require calling external LLM APIs. Codex should simulate multiple expert roles, converge on candidate designs, and output schema-valid factor specs.

## Context

QuantLab uses daily A-share OHLCV-style data and downstream fixed validation. The LLM should propose diverse, explainable factor designs. A local compiler will turn accepted specs into code, and local validators will decide whether a factor is accepted.

The LLM does not decide final validity. It only proposes specs. Local validators decide whether specs are accepted.

## Multi-Role Deliberation

Before producing specs, internally run these roles:

1. **Alpha Researcher**: proposes return-ranking signals and residual alpha ideas.
2. **Risk Researcher**: proposes drawdown, liquidity, volatility, and bad-trade filters.
3. **Portfolio PM**: checks whether each idea can improve the current baseline rather than only standalone IC.
4. **Data/Leakage Reviewer**: rejects future-looking, hardcoded, unavailable, or fragile data assumptions.
5. **Implementation Engineer**: keeps every idea inside supported operators and vectorizable code generation.
6. **Validation Judge**: assigns the correct `role` and expected acceptance metric.

The roles should disagree briefly and resolve conflicts before final specs. Do not include long debate transcripts unless the user asks for them. Keep the final visible rationale concise.

## Output Modes

Use one of two modes:

### Spec-only mode

Use this when the user asks for raw specs or batch generation. Output only JSONL. Each line must be one complete JSON object. Do not output markdown, prose, code fences, Python code, or explanations outside the JSONL.

### Review-plus-spec mode

Use this when the user asks for discussion, comparison, or planning. Output:

1. A concise role-review summary.
2. A short decision or next action.
3. A JSONL block containing the final specs.

The JSONL block must still contain only parseable JSON lines.

## Required JSON Fields

- `name`: snake_case string, stable and descriptive.
- `role`: one of `alpha_ranker`, `risk_filter`, `entry_confirmation`, `regime_gate`, `residual_alpha`.
- `hypothesis`: concise market behavior hypothesis.
- `inputs`: list of allowed fields.
- `operator`: one supported operator family.
- `windows`: list of positive integers.
- `transforms`: list of supported transforms.
- `formula`: structured object describing how inputs/operators/transforms compose.
- `direction`: one of `higher_is_better`, `lower_is_better`, `higher_is_risk`, `gate_true_is_allowed`.
- `expected_effect`: what validation should improve.
- `failure_modes`: list of plausible failure modes.
- `novelty_note`: how this differs from simple MA, RSI, Bollinger, and momentum variants.
- `validator_hint`: concise hint for the role-aware validator.

## Allowed Inputs

- `open`
- `high`
- `low`
- `close`
- `volume`
- `amount`
- `factor`

## Allowed Roles

`alpha_ranker`: intended to rank stocks by expected forward return.

`risk_filter`: intended to identify names or regimes to avoid.

`entry_confirmation`: intended to confirm baseline-selected entries.

`regime_gate`: intended to change exposure or eligibility by environment.

`residual_alpha`: intended to add information not already explained by existing Alpha/Kronos/RD signals.

## Allowed Operators

- `ma_deviation`
- `bollinger_position`
- `range_close_position`
- `return`
- `return_acceleration`
- `cross_window_disagreement`
- `realized_volatility`
- `range_volatility`
- `asymmetric_up_down_volatility`
- `volume_zscore`
- `volume_price_divergence`
- `amihud_proxy`
- `liquidity_shock_reversal`
- `regime_gated_interaction`

## Allowed Transforms

- `rolling_zscore`
- `rolling_rank`
- `cross_sectional_rank`
- `winsorize`
- `sigmoid`
- `tanh`
- `clip`
- `rolling_quantile_gate`
- `neutralize_by_market`

## Diversity Requirements

In a batch of specs:

- Use all roles if the batch size is at least 20.
- At most 20 percent of specs may be simple single-operator MA/RSI/Bollinger-like variants.
- At least half of specs should combine two information families, such as price location plus volume, volatility plus reversal, or liquidity plus return acceleration.
- Avoid only changing window lengths.
- Avoid hardcoded dates, hardcoded instruments, external data, or future labels.
- Include at least one `risk_filter` and one `entry_confirmation` when generating 10 or more specs.
- If a spec is only a simple indicator with a transform, require a strong `novelty_note` or reject it.

## Deliberation Checklist

For every candidate, answer internally:

- What role is this factor serving?
- Which baseline behavior should it improve?
- Can the local compiler build this from the supported operator set?
- Is there any data leakage or future dependency?
- Is this materially different from MA/RSI/Bollinger/momentum variants?
- What validation metric would prove it useful?

Reject candidates that fail any of these checks.

## Output Example

{"name":"liquidity_shock_reversal_20_5","role":"risk_filter","hypothesis":"A short-term rebound after a large negative return is less reliable when volume-adjusted illiquidity has also spiked, because forced trading pressure can persist.","inputs":["close","volume","amount"],"operator":"liquidity_shock_reversal","windows":[5,20],"transforms":["rolling_zscore","cross_sectional_rank","clip"],"formula":{"base":"return_5","gate":"amihud_proxy_zscore_20","composition":"negative_return_reversal_penalized_by_liquidity_shock"},"direction":"higher_is_risk","expected_effect":"Reduce drawdown and bad-trade rate when used as a filter on baseline long candidates.","failure_modes":["May over-filter legitimate rebounds after broad market selloffs.","Amount data quality can weaken the liquidity proxy."],"novelty_note":"Combines reversal with liquidity pressure rather than using pure price deviation or RSI.","validator_hint":"Evaluate as baseline filter: drawdown_delta, bad_trade_filter_rate, opportunity_retention."}

## Final Instruction

When producing final specs, every JSONL line must parse as JSON.
