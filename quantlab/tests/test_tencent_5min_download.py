from pathlib import Path

import pandas as pd

from quantlab.data.tencent_5min_download import normalize_rows, qlib_to_tencent, read_symbols_file, write_summary


def test_qlib_to_tencent():
    assert qlib_to_tencent("SH600000") == "sh600000"
    assert qlib_to_tencent("sz000001") == "sz000001"
    assert qlib_to_tencent("BJ430001") is None


def test_read_symbols_file_dedupes_and_skips_comments(tmp_path: Path):
    path = tmp_path / "symbols.txt"
    path.write_text("# comment\nsh600000\nSZ000001,extra\nSH600000\n\n", encoding="utf-8")

    assert read_symbols_file(path) == ["SH600000", "SZ000001"]


def test_normalize_rows_converts_tencent_m5_payload():
    rows = [
        ["202606021500", "10.0", "10.2", "10.3", "9.9", "123"],
        ["202606031500", "11.0", "11.2", "11.3", "10.9", "1"],
        ["202606041500", "12.0", "12.2", "12.3", "11.9", "1"],
        ["bad-ts", "12.0", "12.2", "12.3", "11.9", "1"],
    ]

    df = normalize_rows("SH600000", rows, "2026-06-02", "2026-06-03")

    assert df["date"].tolist() == ["2026-06-02 15:00:00", "2026-06-03 15:00:00"]
    assert df["symbol"].tolist() == ["SH600000", "SH600000"]
    assert df["volume"].tolist() == [12300.0, 100.0]
    assert df["amount"].tolist() == [10.2 * 12300.0, 11.2 * 100.0]
    assert df["adjustflag"].tolist() == [3, 3]


def test_write_summary(tmp_path: Path):
    write_summary(tmp_path, [{"symbol": "SH600000", "code": "sh600000", "status": "ok", "rows": 2}])

    out = pd.read_csv(tmp_path / "_download_summary.csv")
    assert out.to_dict("records") == [{"symbol": "SH600000", "code": "sh600000", "status": "ok", "rows": 2}]
