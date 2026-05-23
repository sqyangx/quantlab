# Factor-Spec Pipeline

The Factor-Spec Pipeline is a deterministic alternative path for RD-Agent-style
factor discovery. LLMs or local research prompts generate structured
`factor_spec` JSONL records, and QuantLab compiles those records into restricted
`compute_factor(ohlcv)` Python modules.

This keeps exploratory idea generation separate from code execution and final
validation.

## Flow

```text
local skill or offline LLM batch
  -> factor_spec JSONL
  -> schema validation and deduplication
  -> deterministic compiler
  -> sampled smoke test
  -> role-aware full validation
  -> factor registry
```

## Files

- `quantlab/skills/factor_spec_generator/SKILL.md`: local multi-role generation
  instructions.
- `quantlab/skills/factor_spec_generator/factor_spec_schema.yaml`: allowed
  fields, roles, operators, transforms, and directions.
- `quantlab/signal/factor_spec.py`: shared validation, compilation, and smoke
  test helpers.
- `scripts/validate_factor_specs.py`: normalize and reject invalid JSONL specs.
- `scripts/compile_factor_specs.py`: compile normalized specs into factor code.
- `scripts/smoke_test_factor_specs.py`: run sampled execution checks on
  synthetic data or local Qlib data.
- `data/factor_specs/examples/example_specs_20260523.jsonl`: minimal example
  input.

## Example

```bash
python scripts/validate_factor_specs.py \
  --input data/factor_specs/examples/example_specs_20260523.jsonl \
  --output /tmp/factor_specs.normalized.jsonl \
  --rejected /tmp/factor_specs.rejected.csv

python scripts/compile_factor_specs.py \
  --input /tmp/factor_specs.normalized.jsonl \
  --output-dir /tmp/factor_spec_factors \
  --manifest /tmp/factor_spec_manifest.csv

python scripts/smoke_test_factor_specs.py \
  --code-dir /tmp/factor_spec_factors \
  --output /tmp/factor_spec_smoke.csv \
  --sandbox subprocess \
  --sample-size 40 \
  --lookback-days 260
```

For real Qlib data, pass `--data-dir`, `--market`, and `--anchor-date`.
