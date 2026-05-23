from quantlab.signal.factor_spec import (
    compile_spec_to_code,
    load_schema,
    make_synthetic_ohlcv,
    smoke_test_code_dir,
    validate_specs,
)


def _valid_spec(name="ma_reversion_20d_rank"):
    return {
        "name": name,
        "role": "alpha_ranker",
        "hypothesis": "A simple mean reversion factor for compiler testing.",
        "inputs": ["close"],
        "operator": "ma_deviation",
        "windows": [20],
        "transforms": ["winsorize", "cross_sectional_rank"],
        "formula": {"type": "operator", "operator": "ma_deviation", "window": 20},
        "direction": "lower_is_better",
        "expected_effect": "Lower moving-average deviation should be preferred.",
        "failure_modes": ["momentum regime"],
        "novelty_note": "Test-only baseline.",
        "validator_hint": {"primary_metric": "rank_ic", "validation_mode": "alpha_ranker"},
    }


def test_validate_specs_accepts_and_normalizes_valid_spec():
    result = validate_specs([_valid_spec()], load_schema())

    assert len(result.accepted) == 1
    assert not result.rejected
    assert result.accepted[0]["spec_id"]
    assert result.accepted[0]["lookback_days"] == 25


def test_validate_specs_rejects_duplicate_signature():
    result = validate_specs([_valid_spec("factor_a"), _valid_spec("factor_b")], load_schema())

    assert len(result.accepted) == 1
    assert len(result.rejected) == 1
    assert result.rejected[0]["__reject_reason__"] == "duplicate_signature"


def test_compile_spec_to_code_has_compute_factor():
    spec = validate_specs([_valid_spec()], load_schema()).accepted[0]
    code = compile_spec_to_code(spec)

    namespace = {}
    exec(code, namespace)
    values = namespace["compute_factor"](make_synthetic_ohlcv(symbol_count=8, days=80))

    assert len(values) == 8
    assert values.notna().all()


def test_smoke_test_code_dir_passes_compiled_spec(tmp_path):
    spec = validate_specs([_valid_spec()], load_schema()).accepted[0]
    code_dir = tmp_path / "factors"
    code_dir.mkdir()
    (code_dir / "ma_reversion_20d_rank.py").write_text(compile_spec_to_code(spec), encoding="utf-8")

    rows = smoke_test_code_dir(code_dir, make_synthetic_ohlcv(symbol_count=12, days=80), sandbox="inprocess")

    assert len(rows) == 1
    assert rows[0].success, rows[0].error
    assert rows[0].coverage == 1.0
