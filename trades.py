"""
Trades management module.
Handles loading, saving, and managing trade history.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import re


# Default trades file
TRADES_FILE = "Trades_Freedom.xlsx"


def parse_currency_value(value: str) -> float:
    """Parse currency string like '€97.95' to float."""
    if pd.isna(value) or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    # Remove currency symbols and parse
    cleaned = re.sub(r'[€$£,\s]', '', str(value))
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def load_trades(file_path: Optional[str] = None) -> pd.DataFrame:
    """
    Load trades from Excel file.

    Returns DataFrame with columns:
    - trade_id: Trade ID number
    - order_id: Order ID number
    - timestamp: DateTime of trade
    - ticker: Instrument ticker
    - direction: 'buy' or 'sell'
    - price: Trade price
    - quantity: Number of shares
    - amount: Total trade amount
    - fee: Transaction fee
    - profit: Realized profit (for sells)
    """
    if file_path is None:
        file_path = TRADES_FILE

    path = Path(file_path)
    if not path.exists():
        # Return empty DataFrame with correct columns
        return pd.DataFrame(columns=[
            "trade_id", "order_id", "timestamp", "ticker", "direction",
            "price", "quantity", "amount", "fee", "profit"
        ])

    # Read Excel file
    df = pd.read_excel(file_path)

    # Normalize column names
    df.columns = df.columns.str.strip().str.lower()

    # Expected columns mapping
    column_rename = {
        "trade#": "trade_id",
        "order#": "order_id",
        "time": "timestamp",
        "ticker": "ticker",
        "direction": "direction",
        "price": "price",
        "quantity": "quantity",
        "amount": "amount",
        "fee": "fee",
        "profit": "profit",
    }

    # Rename columns
    rename_map = {}
    for old_name, new_name in column_rename.items():
        if old_name in df.columns:
            rename_map[old_name] = new_name

    df = df.rename(columns=rename_map)

    # Parse timestamp
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="%d.%m.%Y %H:%M:%S", errors="coerce")

    # Parse numeric columns
    if "trade_id" in df.columns:
        df["trade_id"] = pd.to_numeric(df["trade_id"], errors="coerce").fillna(0).astype(int)
    if "order_id" in df.columns:
        df["order_id"] = pd.to_numeric(df["order_id"], errors="coerce").fillna(0).astype(int)
    if "price" in df.columns:
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)
    if "quantity" in df.columns:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

    # Parse currency columns
    if "fee" in df.columns:
        df["fee"] = df["fee"].apply(parse_currency_value)
    if "profit" in df.columns:
        df["profit"] = df["profit"].apply(parse_currency_value)

    # Clean direction column
    if "direction" in df.columns:
        df["direction"] = df["direction"].str.lower().str.strip()

    # Sort by timestamp descending (most recent first)
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp", ascending=False)

    return df.reset_index(drop=True)


def save_trades(df: pd.DataFrame, file_path: Optional[str] = None) -> bool:
    """
    Save trades DataFrame to Excel file.

    Args:
        df: DataFrame with trades
        file_path: Path to save (defaults to TRADES_FILE)

    Returns:
        True if successful, False otherwise
    """
    if file_path is None:
        file_path = TRADES_FILE

    try:
        # Prepare DataFrame for export
        export_df = df.copy()

        # Rename columns back to original format
        column_rename = {
            "trade_id": "Trade#",
            "order_id": "Order#",
            "timestamp": "Time",
            "ticker": "Ticker",
            "direction": "Direction",
            "price": "Price",
            "quantity": "Quantity",
            "amount": "Amount",
            "fee": "Fee",
            "profit": "Profit",
        }

        export_df = export_df.rename(columns=column_rename)

        # Format timestamp
        if "Time" in export_df.columns:
            export_df["Time"] = export_df["Time"].dt.strftime("%d.%m.%Y %H:%M:%S")

        # Format currency columns
        if "Fee" in export_df.columns:
            export_df["Fee"] = export_df["Fee"].apply(lambda x: f"€{x:.2f}" if x else "€0")
        if "Profit" in export_df.columns:
            export_df["Profit"] = export_df["Profit"].apply(lambda x: f"€{x:.2f}" if x else "€0")

        # Sort by time ascending for export
        if "Time" in export_df.columns:
            export_df = export_df.sort_values("Time", ascending=True)

        # Save to Excel
        export_df.to_excel(file_path, index=False)
        return True

    except Exception as e:
        print(f"Error saving trades: {e}")
        return False


def add_trade(
    df: pd.DataFrame,
    ticker: str,
    direction: str,
    price: float,
    quantity: int,
    fee: float = 0,
    timestamp: Optional[datetime] = None,
    trade_id: Optional[int] = None,
    order_id: Optional[int] = None,
) -> pd.DataFrame:
    """
    Add a new trade to the DataFrame.

    Args:
        df: Existing trades DataFrame
        ticker: Instrument ticker (e.g., "VWCE.EU")
        direction: "buy" or "sell"
        price: Trade price
        quantity: Number of shares
        fee: Transaction fee (default 0)
        timestamp: Trade time (default now)
        trade_id: Trade ID (auto-generated if None)
        order_id: Order ID (auto-generated if None)

    Returns:
        Updated DataFrame with new trade
    """
    if timestamp is None:
        timestamp = datetime.now()

    # Auto-generate IDs if not provided
    if trade_id is None:
        max_id = df["trade_id"].max() if len(df) > 0 and "trade_id" in df.columns else 0
        trade_id = int(max_id) + 1 if not pd.isna(max_id) else 1

    if order_id is None:
        max_id = df["order_id"].max() if len(df) > 0 and "order_id" in df.columns else 0
        order_id = int(max_id) + 1 if not pd.isna(max_id) else 1

    amount = price * quantity

    new_trade = pd.DataFrame([{
        "trade_id": trade_id,
        "order_id": order_id,
        "timestamp": timestamp,
        "ticker": ticker,
        "direction": direction.lower(),
        "price": price,
        "quantity": quantity,
        "amount": amount,
        "fee": fee,
        "profit": 0,  # Profit calculated elsewhere for sells
    }])

    # Concatenate and sort
    result = pd.concat([df, new_trade], ignore_index=True)
    result = result.sort_values("timestamp", ascending=False).reset_index(drop=True)

    return result


def delete_trade(df: pd.DataFrame, trade_id: int) -> pd.DataFrame:
    """
    Delete a trade by ID.

    Args:
        df: Trades DataFrame
        trade_id: ID of trade to delete

    Returns:
        Updated DataFrame without the deleted trade
    """
    return df[df["trade_id"] != trade_id].reset_index(drop=True)


def get_trades_summary(df: pd.DataFrame) -> dict:
    """Get summary statistics for trades."""
    if df.empty:
        return {
            "total_trades": 0,
            "total_buys": 0,
            "total_sells": 0,
            "total_volume": 0,
            "total_fees": 0,
            "total_profit": 0,
            "tickers_traded": [],
        }

    buys = df[df["direction"] == "buy"]
    sells = df[df["direction"] == "sell"]

    return {
        "total_trades": len(df),
        "total_buys": len(buys),
        "total_sells": len(sells),
        "total_volume": df["amount"].sum(),
        "total_fees": df["fee"].sum(),
        "total_profit": df["profit"].sum(),
        "tickers_traded": df["ticker"].unique().tolist(),
    }


def get_trades_by_ticker(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Get all trades for a specific ticker."""
    return df[df["ticker"] == ticker].reset_index(drop=True)


def get_trades_by_date_range(
    df: pd.DataFrame,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> pd.DataFrame:
    """Get trades within a date range."""
    result = df.copy()

    if start_date is not None:
        result = result[result["timestamp"] >= start_date]

    if end_date is not None:
        result = result[result["timestamp"] <= end_date]

    return result.reset_index(drop=True)


if __name__ == "__main__":
    # Test loading trades
    trades = load_trades()
    print(f"Loaded {len(trades)} trades")
    print("\nColumns:", trades.columns.tolist())
    print("\nFirst 5 trades:")
    print(trades.head().to_string())
    print("\nSummary:")
    print(get_trades_summary(trades))
