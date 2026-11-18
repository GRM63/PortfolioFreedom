"""
Portfolio data loading from Excel file.
Reads platform prices and values directly from Excel for accurate portfolio valuation.
"""

import pandas as pd
from pathlib import Path
from typing import Optional
from config import PORTFOLIO_FILE, TICKER_MAPPING

# Lower-cased Excel header -> internal column name (Freedom platform export)
PORTFOLIO_COLUMNS = {
    "ticker": "ticker",
    "qty": "quantity",
    "entry price": "entry_price",
    "price": "platform_price",
    "value": "platform_value",
    "share (%)": "platform_share",
    "profit": "platform_profit",
    "growth": "platform_growth",
}

# Internal column name -> header used when exporting
PORTFOLIO_EXPORT_HEADERS = {
    "ticker": "Ticker",
    "quantity": "Qty",
    "entry_price": "Entry Price",
    "platform_price": "Price",
    "platform_value": "Value",
    "platform_profit": "Profit",
    "platform_growth": "Growth",
    "entry_value": "Entry Value",
}


def get_yfinance_ticker(freedom_ticker: str) -> str:
    """Convert Freedom platform ticker to yfinance symbol."""
    return TICKER_MAPPING.get(freedom_ticker, freedom_ticker)


def load_portfolio(file_path: Optional[str] = None) -> pd.DataFrame:
    """
    Load portfolio holdings from Excel file.

    The Excel file contains platform data with columns:
    - Ticker, Qty, Entry Price, Price, Value, Share (%), Profit, Growth

    Returns DataFrame with columns:
    - ticker: Original Freedom ticker
    - yf_ticker: yfinance compatible ticker
    - quantity: Number of shares
    - entry_price: Average purchase price
    - entry_value: Total entry value (quantity * entry_price)
    - platform_price: Current price from platform (EUR)
    - platform_value: Current value from platform (EUR)
    - platform_profit: Profit/loss from platform (EUR)
    - platform_growth: Growth percentage from platform
    """
    if file_path is None:
        file_path = PORTFOLIO_FILE

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Portfolio file not found: {file_path}")

    # `with` closes the file handle as soon as we're done reading
    with pd.ExcelFile(file_path) as xl:
        keywords = ("portfolio", "holdings", "positions", "summary")
        portfolio_sheet = next(
            (name for name in xl.sheet_names if any(k in name.lower() for k in keywords)),
            xl.sheet_names[0],
        )
        df = pd.read_excel(xl, sheet_name=portfolio_sheet)

    # Expected columns: Ticker, Qty, Entry Price, Price, Value, Share (%), Profit, Growth
    # Normalize column names
    df.columns = df.columns.str.strip().str.lower()

    # rename() ignores keys that aren't present, so no need to filter first
    df = df.rename(columns=PORTFOLIO_COLUMNS)

    # Clean up data
    df = df.dropna(subset=["ticker"])

    # Convert types
    df["ticker"] = df["ticker"].astype(str).str.strip()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["entry_price"] = pd.to_numeric(df["entry_price"], errors="coerce").fillna(0)
    df["platform_price"] = pd.to_numeric(df.get("platform_price", 0), errors="coerce").fillna(0)
    df["platform_value"] = pd.to_numeric(df.get("platform_value", 0), errors="coerce").fillna(0)
    df["platform_profit"] = pd.to_numeric(df.get("platform_profit", 0), errors="coerce").fillna(0)
    df["platform_growth"] = pd.to_numeric(df.get("platform_growth", 0), errors="coerce").fillna(0)

    # Filter out rows with zero quantity
    df = df[df["quantity"] > 0]

    # Add yfinance ticker
    df["yf_ticker"] = df["ticker"].apply(get_yfinance_ticker)

    # Calculate entry value
    df["entry_value"] = df["quantity"] * df["entry_price"]

    # Reset index
    df = df.reset_index(drop=True)

    return df


def get_portfolio_summary(df: pd.DataFrame) -> dict:
    """Get portfolio summary statistics."""
    return {
        "total_holdings": len(df),
        "total_entry_value": df["entry_value"].sum(),
        "tickers": df["ticker"].tolist(),
    }


if __name__ == "__main__":
    # Test loading
    try:
        portfolio = load_portfolio()
        print("Portfolio loaded successfully:")
        print(portfolio.to_string())
        print("\nSummary:")
        print(get_portfolio_summary(portfolio))
    except Exception as e:
        print(f"Error loading portfolio: {e}")
