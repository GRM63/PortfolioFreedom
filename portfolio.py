"""
Portfolio data loading from Excel file.
Reads platform prices and values directly from Excel for accurate portfolio valuation.
"""

import pandas as pd
from pathlib import Path
from typing import Optional
from config import PORTFOLIO_FILE, TICKER_MAPPING


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

    # Read Excel file
    xl = pd.ExcelFile(file_path)

    # Try to find the main portfolio sheet
    portfolio_sheet = None
    for name in xl.sheet_names:
        name_lower = name.lower()
        if any(keyword in name_lower for keyword in ["portfolio", "holdings", "positions", "summary"]):
            portfolio_sheet = name
            break

    if portfolio_sheet is None:
        portfolio_sheet = xl.sheet_names[0]

    df = pd.read_excel(xl, sheet_name=portfolio_sheet)

    # Expected columns: Ticker, Qty, Entry Price, Price, Value, Share (%), Profit, Growth
    # Normalize column names
    df.columns = df.columns.str.strip().str.lower()

    # Direct column mapping for Freedom platform export
    column_rename = {
        "ticker": "ticker",
        "qty": "quantity",
        "entry price": "entry_price",
        "price": "platform_price",
        "value": "platform_value",
        "share (%)": "platform_share",
        "profit": "platform_profit",
        "growth": "platform_growth",
    }

    # Rename columns that exist
    rename_map = {}
    for old_name, new_name in column_rename.items():
        if old_name in df.columns:
            rename_map[old_name] = new_name

    df = df.rename(columns=rename_map)

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
