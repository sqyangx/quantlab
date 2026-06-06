from pathlib import Path

import pandas as pd

from quantlab.data.baostock_daily_download import normalize_rows, qlib_to_baostock, read_symbols_file, write_summary


def test_qlib_to_baostock():
    assert qlib_to_baostock("SH600000") == "sh.600000"
    assert qlib_to_baostock("sz000001") == "sz.000001"
    assert qlib_to_baostock("BJ430001") is None


def test_read_symbols_file_dedupes_and_skips_comments(tmp_path: Path):
    path = tmp_path / "symbols.txt"
    path.write_text("# comment\nsh600000\nSZ000001,extra\nSH600000\n\n", encoding="utf-8")

    assert read_symbols_file(path) == ["SH600000", "SZ000001"]


def test_normalize_rows_converts_daily_payload():
    rows = [
        ["2026-06-02", "10.0", "10.3", "9.9", "10.2", "1000", "10200"],
        ["2026-06-02", "10.0", "10.3", "9.9", "10.2", "1000", "10200"],
        ["2026-06-03", "bad", "11.3", "10.9", "11.2", "100", "1120"],
    ]

    df = normalize_rows("SH600000", rows)

    assert df["date"].tolist() == ["2026-06-02", "2026-06-03"]
    assert df["symbol"].tolist() == ["SH600000", "SH600000"]
    assert df["close"].tolist() == [10.2, 11.2]
    assert pd.isna(df["open"].iloc[1])


def test_write_summary(tmp_path: Path):
    write_summary(tmp_path, [{"symbol": "SH600000", "code": "sh.600000", "status": "ok", "rows": 2}])

    out = pd.read_csv(tmp_path / "_download_summary.csv")
    assert out.to_dict("records") == [{"symbol": "SH600000", "code": "sh.600000", "status": "ok", "rows": 2}]
