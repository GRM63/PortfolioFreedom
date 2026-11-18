"""Tests for trade loading/saving and Excel import."""

import io
from datetime import datetime

import pandas as pd
import pytest

from file_manager import export_trades_excel, import_trades_excel
from trades import add_trade, empty_trades, load_trades, normalize_trades, save_trades


def make_trades(rows):
    """Build an internal-format trades DataFrame from (id, timestamp, ticker) tuples."""
    df = empty_trades()
    for trade_id, ts, ticker in rows:
        df = add_trade(df, ticker=ticker, direction="buy", price=10.0, quantity=2,
                       fee=1.5, timestamp=ts, trade_id=trade_id, order_id=trade_id)
    return df


def to_upload(df: pd.DataFrame) -> io.BytesIO:
    """Simulate a Streamlit UploadedFile containing df as an .xlsx."""
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return buf


@pytest.fixture
def trades_path(tmp_path):
    return str(tmp_path / "trades.xlsx")


def test_save_load_roundtrip(trades_path):
    df = make_trades([(1, datetime(2025, 12, 31, 9, 0), "AMD.US"),
                      (2, datetime(2026, 1, 2, 9, 0), "VWCE.EU")])
    assert save_trades(df, trades_path)

    loaded = load_trades(trades_path)
    assert loaded["trade_id"].tolist() == [2, 1]          # newest first
    assert loaded["fee"].tolist() == [1.5, 1.5]
    assert loaded["timestamp"].iloc[0] == pd.Timestamp(2026, 1, 2, 9, 0)


def test_saved_file_is_chronological_across_months(trades_path):
    # "02.01.2026" < "31.12.2025" as strings, so a string sort gets this wrong.
    df = make_trades([(1, datetime(2025, 12, 31), "A"),
                      (2, datetime(2026, 1, 2), "B"),
                      (3, datetime(2025, 11, 15), "C")])
    save_trades(df, trades_path)

    raw = pd.read_excel(trades_path)
    assert raw["Trade#"].tolist() == [3, 1, 2]


def test_export_is_chronological():
    df = make_trades([(1, datetime(2025, 12, 31), "A"),
                      (2, datetime(2026, 1, 2), "B")])
    raw = pd.read_excel(io.BytesIO(export_trades_excel(df)))
    assert raw["Trade#"].tolist() == [1, 2]


def test_merge_import_keeps_existing_trades(trades_path):
    save_trades(make_trades([(1, datetime(2025, 1, 1), "A"),
                             (2, datetime(2025, 1, 2), "B")]), trades_path)

    # Upload contains one duplicate (id 2) and one new trade (id 3)
    upload_df = pd.read_excel(io.BytesIO(export_trades_excel(
        make_trades([(2, datetime(2025, 1, 2), "B"),
                     (3, datetime(2025, 1, 3), "C")]))))
    ok, msg, _ = import_trades_excel(to_upload(upload_df), trades_path, merge=True)

    assert ok, msg
    assert "1 new" in msg
    assert sorted(load_trades(trades_path)["trade_id"]) == [1, 2, 3]


def test_merge_import_accepts_column_aliases(trades_path):
    save_trades(make_trades([(1, datetime(2025, 1, 1), "A")]), trades_path)

    upload_df = pd.DataFrame({
        "Symbol": ["HOOD.US"], "Side": ["BUY"], "Price": [20.0],
        "Qty": [3], "Time": ["05.02.2025 10:00:00"],
    })
    ok, msg, _ = import_trades_excel(to_upload(upload_df), trades_path, merge=True)

    assert ok, msg
    loaded = load_trades(trades_path)
    assert set(loaded["ticker"]) == {"A", "HOOD.US"}
    hood = loaded[loaded["ticker"] == "HOOD.US"].iloc[0]
    assert hood["direction"] == "buy"
    assert hood["amount"] == 60.0


def test_replace_import(trades_path):
    save_trades(make_trades([(1, datetime(2025, 1, 1), "A")]), trades_path)
    upload_df = pd.read_excel(io.BytesIO(export_trades_excel(
        make_trades([(9, datetime(2025, 3, 1), "Z")]))))

    ok, _, _ = import_trades_excel(to_upload(upload_df), trades_path, merge=False)

    assert ok
    assert load_trades(trades_path)["trade_id"].tolist() == [9]


def test_import_rejects_missing_columns(trades_path):
    ok, msg, df = import_trades_excel(to_upload(pd.DataFrame({"Ticker": ["A"]})), trades_path)
    assert not ok and df is None
    assert "Missing required columns" in msg


def test_normalize_parses_currency_strings():
    df = normalize_trades(pd.DataFrame({
        "Ticker": ["A"], "Direction": ["Sell"], "Price": [1], "Quantity": [1],
        "Fee": ["€1,234.50"], "Profit": [""],
    }))
    assert df.loc[0, "fee"] == 1234.5
    assert df.loc[0, "profit"] == 0.0
