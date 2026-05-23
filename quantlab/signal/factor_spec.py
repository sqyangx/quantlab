"""Factor-spec validation, compilation, and smoke-test helpers."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml


DEFAULT_SCHEMA = Path(__file__).resolve().parent.parent / "skills" / "factor_spec_generator" / "factor_spec_schema.yaml"

SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class SpecValidationResult:
    accepted: list[dict[str, Any]]
    rejected: list[dict[str, Any]]


@dataclass
class SmokeResult:
    name: str
    success: bool
    error: str = ""
    elapsed_ms: int = 0
    coverage: float = 0.0
    nan_rate: float = 0.0
    constant: bool = False
    n_values: int = 0


def load_schema(path: str | Path = DEFAULT_SCHEMA) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError as exc:
                rows.append({"__invalid_json__": text, "__line_no__": line_no, "__error__": str(exc)})
                continue
            if isinstance(row, dict):
                row["__line_no__"] = line_no
                rows.append(row)
            else:
                rows.append({"__invalid_json__": text, "__line_no__": line_no, "__error__": "line is not a JSON object"})
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            clean = {k: v for k, v in row.items() if not k.startswith("__")}
            f.write(json.dumps(clean, ensure_ascii=False, sort_keys=True) + "\n")


def write_rejections(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["line_no", "name", "reason", "detail"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "line_no": row.get("__line_no__", ""),
                "name": row.get("name", ""),
                "reason": row.get("__reject_reason__", ""),
                "detail": row.get("__reject_detail__", ""),
            })


def _reject(row: dict[str, Any], reason: str, detail: str) -> dict[str, Any]:
    out = dict(row)
    out["__reject_reason__"] = reason
    out["__reject_detail__"] = detail
    return out


def _stable_signature(spec: dict[str, Any]) -> str:
    payload = {
        "role": spec.get("role"),
        "inputs": sorted(spec.get("inputs") or []),
        "operator": spec.get("operator"),
        "windows": spec.get("windows"),
        "transforms": sorted(spec.get("transforms") or []),
        "formula": spec.get("formula"),
        "direction": spec.get("direction"),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def validate_specs(specs: list[dict[str, Any]], schema: dict[str, Any]) -> SpecValidationResult:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_signatures: set[str] = set()

    required = set(schema.get("required_fields") or [])
    roles = set(schema.get("roles") or [])
    inputs = set(schema.get("inputs") or [])
    operators = set(schema.get("operators") or [])
    transforms = set(schema.get("transforms") or [])
    directions = set(schema.get("directions") or [])

    for row in specs:
        if "__invalid_json__" in row:
            rejected.append(_reject(row, "invalid_json", row.get("__error__", "")))
            continue

        missing = sorted(k for k in required if k not in row)
        if missing:
            rejected.append(_reject(row, "missing_fields", ",".join(missing)))
            continue

        name = str(row.get("name", "")).strip()
        if not SNAKE_RE.match(name):
            rejected.append(_reject(row, "bad_name", "name must be snake_case and start with a letter"))
            continue
        if name in seen_names:
            rejected.append(_reject(row, "duplicate_name", name))
            continue

        if row.get("role") not in roles:
            rejected.append(_reject(row, "bad_role", str(row.get("role"))))
            continue
        if row.get("operator") not in operators:
            rejected.append(_reject(row, "bad_operator", str(row.get("operator"))))
            continue
        if row.get("direction") not in directions:
            rejected.append(_reject(row, "bad_direction", str(row.get("direction"))))
            continue

        row_inputs = row.get("inputs")
        if not isinstance(row_inputs, list) or not row_inputs:
            rejected.append(_reject(row, "bad_inputs", "inputs must be a non-empty list"))
            continue
        bad_inputs = sorted(str(x) for x in row_inputs if x not in inputs)
        if bad_inputs:
            rejected.append(_reject(row, "bad_inputs", ",".join(bad_inputs)))
            continue

        windows = row.get("windows")
        if not isinstance(windows, list) or not windows or any(not isinstance(x, int) or x <= 0 for x in windows):
            rejected.append(_reject(row, "bad_windows", "windows must be positive integers"))
            continue
        if max(windows) > 756:
            rejected.append(_reject(row, "bad_windows", "max window above 756 trading days"))
            continue

        row_transforms = row.get("transforms")
        if not isinstance(row_transforms, list):
            rejected.append(_reject(row, "bad_transforms", "transforms must be a list"))
            continue
        bad_transforms = sorted(str(x) for x in row_transforms if x not in transforms)
        if bad_transforms:
            rejected.append(_reject(row, "bad_transforms", ",".join(bad_transforms)))
            continue

        if not isinstance(row.get("formula"), dict):
            rejected.append(_reject(row, "bad_formula", "formula must be an object"))
            continue

        sig = _stable_signature(row)
        if sig in seen_signatures:
            rejected.append(_reject(row, "duplicate_signature", sig))
            continue

        clean = {k: v for k, v in row.items() if not k.startswith("__")}
        clean["spec_id"] = sig
        clean["lookback_days"] = max(windows) + 5
        accepted.append(clean)
        seen_names.add(name)
        seen_signatures.add(sig)

    return SpecValidationResult(accepted=accepted, rejected=rejected)


def validate_specs_file(input_path: str | Path, output_path: str | Path, rejected_path: str | Path, schema_path: str | Path = DEFAULT_SCHEMA) -> SpecValidationResult:
    schema = load_schema(schema_path)
    result = validate_specs(read_jsonl(input_path), schema)
    write_jsonl(output_path, result.accepted)
    write_rejections(rejected_path, result.rejected)
    return result


def sanitize_name(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip()).lower()
    name = re.sub(r"_+", "_", name).strip("_")
    if not name or not name[0].isalpha():
        name = f"factor_{name}"
    return name


def compile_spec_to_code(spec: dict[str, Any]) -> str:
    name = sanitize_name(str(spec["name"]))
    role = str(spec["role"])
    operator = str(spec["operator"])
    windows = [int(x) for x in spec["windows"]]
    transforms = [str(x) for x in spec.get("transforms", [])]
    inputs = [str(x) for x in spec.get("inputs", [])]
    direction = str(spec["direction"])
    spec_id = str(spec.get("spec_id") or _stable_signature(spec))
    int(spec.get("lookback_days") or max(windows) + 5)

    return f'''import numpy as np
import pandas as pd
SPEC_ID = {spec_id!r}
OPERATOR = {operator!r}
DIRECTION = {direction!r}
REQUIRED_FIELDS = {inputs!r}
WINDOWS = {windows!r}
TRANSFORMS = {transforms!r}
def _div(a, b):
    return a / b.replace(0, np.nan)
def _last(s):
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    return np.nan if s.empty else float(s.iloc[-1])
def _prep(df):
    df = df.copy()
    if any(field not in df.columns for field in REQUIRED_FIELDS) or len(df) < max(WINDOWS) + 2:
        return None
    c = df["close"].astype(float)
    h = df["high"].astype(float) if "high" in df.columns else c
    l = df["low"].astype(float) if "low" in df.columns else c
    v = df["volume"].astype(float) if "volume" in df.columns else pd.Series(1.0, index=df.index)
    a = df["amount"].astype(float) if "amount" in df.columns else c * v
    return c, h, l, v, a
def _calc(df):
    p = _prep(df)
    if p is None: return np.nan
    close, high, low, volume, amount = p
    op = OPERATOR
    w0 = WINDOWS[0]
    w1 = WINDOWS[1] if len(WINDOWS) > 1 else max(w0 * 2, w0 + 1)
    if op == "ma_deviation":
        ma = close.rolling(w0, min_periods=w0).mean()
        return _last(_div(close - ma, ma))
    elif op == "bollinger_position":
        ma = close.rolling(w0, min_periods=w0).mean()
        std = close.rolling(w0, min_periods=w0).std()
        return _last(_div(close - ma, std))
    elif op == "range_close_position":
        return _last((close - low) / (high - low).replace(0, np.nan) - 0.5)
    elif op == "return":
        return _last(close.pct_change(w0))
    elif op == "return_acceleration":
        short_ret = close.pct_change(w0)
        long_ret = close.pct_change(w1) / max(w1 / w0, 1.0)
        return _last(short_ret - long_ret)
    elif op == "cross_window_disagreement":
        return _last(close.pct_change(w0) - close.pct_change(w1))
    elif op == "realized_volatility":
        return _last(close.pct_change().rolling(w0, min_periods=w0).std())
    elif op == "range_volatility":
        return _last(_div(high - low, close).rolling(w0, min_periods=w0).mean())
    elif op == "asymmetric_up_down_volatility":
        ret = close.pct_change()
        up = ret.where(ret > 0, 0.0).rolling(w0, min_periods=w0).std()
        down = ret.where(ret < 0, 0.0).abs().rolling(w0, min_periods=w0).std()
        return _last(up - down)
    elif op == "volume_zscore":
        vol_ma = volume.rolling(w1, min_periods=w1).mean()
        vol_std = volume.rolling(w1, min_periods=w1).std()
        return _last(_div(volume - vol_ma, vol_std))
    elif op == "volume_price_divergence":
        return _last(volume.pct_change(w0) - close.pct_change(w0))
    elif op == "amihud_proxy":
        return _last(_div(close.pct_change().abs(), amount.abs()).rolling(w0, min_periods=w0).mean())
    elif op == "liquidity_shock_reversal":
        ret = close.pct_change(w0)
        illiq = _div(close.pct_change().abs(), amount.abs()).rolling(w1, min_periods=w1).mean()
        illiq_z = _div(illiq - illiq.rolling(w1, min_periods=w1).mean(), illiq.rolling(w1, min_periods=w1).std())
        return _last((-ret) * illiq_z)
    elif op == "regime_gated_interaction":
        return _last(close.pct_change(w0) * _div(high - low, close).rolling(w1, min_periods=w1).mean())
    return np.nan
def _transform(s):
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return s
    if "winsorize" in TRANSFORMS:
        s = s.clip(s.quantile(0.01), s.quantile(0.99))
    if "cross_sectional_rank" in TRANSFORMS or "rolling_rank" in TRANSFORMS:
        s = s.rank(pct=True)
    if "rolling_zscore" in TRANSFORMS:
        std = s.std()
        if std and not np.isnan(std):
            s = (s - s.mean()) / std
    if "sigmoid" in TRANSFORMS:
        s = 1.0 / (1.0 + np.exp(-s.clip(-20, 20)))
    if "tanh" in TRANSFORMS:
        s = np.tanh(s.clip(-20, 20))
    if "clip" in TRANSFORMS:
        s = s.clip(-5, 5)
    if "rolling_quantile_gate" in TRANSFORMS:
        s = s.where(s >= s.quantile(0.8), 0.0)
    return s.replace([np.inf, -np.inf], np.nan).dropna()
def compute_factor(ohlcv):
    values = {{k: _calc(v) for k, v in ohlcv.items() if v is not None and not v.empty}}
    result = pd.Series({{k: v for k, v in values.items() if v == v and np.isfinite(v)}}, dtype=float)
    result = _transform(result)
    return -result if DIRECTION in ("lower_is_better", "higher_is_risk") else result
'''


def compile_specs_file(input_path: str | Path, output_dir: str | Path, manifest_path: str | Path | None = None) -> list[dict[str, Any]]:
    specs = read_jsonl(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for spec in specs:
        if "__invalid_json__" in spec:
            continue
        name = sanitize_name(str(spec["name"]))
        code = compile_spec_to_code(spec)
        code_path = output_dir / f"{name}.py"
        code_path.write_text(code, encoding="utf-8")
        rows.append({
            "name": name,
            "role": spec.get("role", ""),
            "operator": spec.get("operator", ""),
            "code_path": str(code_path),
            "spec_id": spec.get("spec_id", ""),
        })
    if manifest_path:
        manifest = Path(manifest_path)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "role", "operator", "code_path", "spec_id"])
            writer.writeheader()
            writer.writerows(rows)
    return rows


def make_synthetic_ohlcv(symbol_count: int = 40, days: int = 260, seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=days, freq="B")
    out: dict[str, pd.DataFrame] = {}
    for i in range(symbol_count):
        symbol = f"S{i:04d}"
        ret = rng.normal(0.0002, 0.02, size=days)
        close = 10 * np.exp(np.cumsum(ret))
        spread = rng.uniform(0.002, 0.035, size=days)
        high = close * (1 + spread)
        low = close * (1 - spread)
        open_ = close * (1 + rng.normal(0, 0.006, size=days))
        volume = rng.lognormal(12, 0.7, size=days)
        amount = close * volume
        out[symbol] = pd.DataFrame({
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "amount": amount,
            "factor": np.ones(days),
        }, index=dates)
    return out


def load_sample_ohlcv(data_dir: str | None, market: str, anchor_date: str, lookback_days: int, sample_size: int) -> dict[str, pd.DataFrame]:
    if not data_dir:
        return make_synthetic_ohlcv(symbol_count=sample_size, days=lookback_days)
    from quantlab.data.data_manager import DataManager

    dm = DataManager(provider_uri=data_dir, market=market)
    dm.init_qlib()
    data = dm.get_ohlcv_before(anchor_date, lookback_days)
    if sample_size and len(data) > sample_size:
        keys = sorted(data)[:sample_size]
        data = {k: data[k] for k in keys}
    _attach_amount_from_qlib(dm, data, anchor_date)
    return data


def _attach_amount_from_qlib(dm: Any, data: dict[str, pd.DataFrame], anchor_date: str) -> None:
    if not data or all("amount" in df.columns for df in data.values()):
        return
    dates = [df.index.min() for df in data.values() if df is not None and not df.empty]
    if not dates:
        return
    start_date = min(dates)
    instruments = dm._D.instruments(market=dm.market)
    amount_df = dm._D.features(
        instruments,
        ["$amount"],
        start_time=start_date,
        end_time=anchor_date,
        freq="day",
    )
    if amount_df is None or amount_df.empty:
        return
    amount_df.columns = ["amount"]
    for symbol, df in data.items():
        if "amount" in df.columns or symbol not in amount_df.index.get_level_values(0):
            continue
        series = amount_df.loc[symbol]["amount"]
        df["amount"] = series.reindex(df.index)


def smoke_test_code_dir(
    code_dir: str | Path,
    ohlcv: dict[str, pd.DataFrame],
    timeout_sec: int = 60,
    sandbox: str = "subprocess",
    max_lines: int = 220,
) -> list[SmokeResult]:
    from quantlab.signal.signal_rdagent import CodeFactorExecutor

    executor = CodeFactorExecutor(sandbox_mode=sandbox, timeout_sec=timeout_sec)
    results: list[SmokeResult] = []
    universe_size = max(len(ohlcv), 1)
    for path in sorted(Path(code_dir).glob("*.py")):
        code = path.read_text(encoding="utf-8")
        try:
            result = executor.execute_factor(code, ohlcv, max_lines=max_lines)
        except TypeError as exc:
            if "max_lines" not in str(exc):
                raise
            result = executor.execute_factor(code, ohlcv)
        if not result.success or result.values is None:
            results.append(SmokeResult(name=path.stem, success=False, error=result.error, elapsed_ms=result.elapsed_ms))
            continue
        values = result.values.replace([np.inf, -np.inf], np.nan)
        non_na = values.dropna()
        constant = bool(len(non_na) > 1 and non_na.nunique(dropna=True) <= 1)
        results.append(SmokeResult(
            name=path.stem,
            success=not constant and len(non_na) > 0,
            error="constant_output" if constant else "",
            elapsed_ms=result.elapsed_ms,
            coverage=float(len(non_na) / universe_size),
            nan_rate=float(values.isna().mean()) if len(values) else 1.0,
            constant=constant,
            n_values=int(len(non_na)),
        ))
    return results


def write_smoke_results(path: str | Path, rows: list[SmokeResult]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["name", "success", "error", "elapsed_ms", "coverage", "nan_rate", "constant", "n_values"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def add_common_paths() -> None:
    import sys
    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
