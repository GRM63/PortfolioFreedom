"""Tests for portfolio loading and export."""

import io

import pandas as pd

from file_manager import export_portfolio_excel
from portfolio import load_portfolio


def test_load_and_export_roundtrip(tmp_path):
    path = tmp_path / "portfolio.xlsx"
    pd.DataFrame({
        " Ticker ": ["VWCE.EU", "AMD.US", "SOLD.US"],
        "Qty": [10, 5, 0],
        "Entry Price": [100, 120, 50],
        "Price": [110, 150, 60],
        "Value": [1100, 750, 0],
        "Share (%)": [59, 41, 0],
        "Profit": [100, 150, 0],
        "Growth": [10, 25, 0],
    }).to_excel(path, index=False, sheet_name="Holdings")

    df = load_portfolio(str(path))

    assert df["ticker"].tolist() == ["VWCE.EU", "AMD.US"]   # zero qty dropped
    assert df["yf_ticker"].tolist() == ["VWCE.DE", "AMD"]
    assert df["entry_value"].tolist() == [1000, 600]

    exported = pd.read_excel(io.BytesIO(export_portfolio_excel(df)))
    assert "yf_ticker" not in exported.columns
    assert "Share (%)" not in exported.columns
    assert exported["Entry Value"].tolist() == [1000, 600]
