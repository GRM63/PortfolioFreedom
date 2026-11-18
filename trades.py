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


TRADE_COLUMNS = [
    "trade_id", "order_id", "timestamp", "ticker", "direction",
    "price", "quantity", "amount", "fee", "profit",
]

# Lower-cased source column name -> internal column name.
# Several aliases are accepted so exports from other tools can be imported.
COLUMN_ALIASES = {
    "trade#": "trade_id",
    "trade_id": "trade_id",
    "order#": "order_id",
    "order_id": "order_id",
    "time": "timestamp",
    "timestamp": "timestamp",
    "date": "timestamp",
    "ticker": "ticker",
    "symbol": "ticker",
    "instrument": "ticker",
    "direction": "direction",
    "side": "direction",
    "type": "direction",
    "price": "price",
    "quantity": "quantity",
    "qty": "quantity",
    "shares": "quantity",
    "amount": "amount",
    "fee": "fee",
    "profit": "profit",
}

REQUIRED_COLUMNS = ["ticker", "direction", "price", "quantity"]

# Internal column name -> column header used in the Excel file
EXPORT_HEADERS = {
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

TIMESTAMP_FORMAT = "%d.%m.%Y %H:%M:%S"


def empty_trades() -> pd.DataFrame:
    """Return an empty trades DataFrame with the standard columns."""
    return pd.DataFrame(columns=TRADE_COLUMNS)


def _parse_timestamps(series: pd.Series) -> pd.Series:
    """Parse timestamps in the Freedom format, falling back to a day-first guess."""
    parsed = pd.to_datetime(series, format=TIMESTAMP_FORMAT, errors="coerce")
    missing = parsed.isna() & series.notna()
    if missing.any():
        parsed[missing] = pd.to_datetime(series[missing], dayfirst=True, errors="coerce")
    return parsed


def normalize_trades(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Convert a raw trades sheet (as read from Excel) into the internal format.

    Column names are matched case-insensitively against COLUMN_ALIASES; the
    first alias found for each internal column wins. Raises ValueError if any
    of REQUIRED_COLUMNS is missing.
    """
    df = raw.copy()
    df.columns = df.columns.astype(str).str.strip().str.lower()

    rename_map = {}
    for col in df.columns:
        target = COLUMN_ALIASES.get(col)
        if target and target not in rename_map.values():
            rename_map[col] = target
    df = df.rename(columns=rename_map)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns {missing}. Found: {list(raw.columns)}")

    if "timestamp" in df.columns:
        df["timestamp"] = _parse_timestamps(df["timestamp"])

    for col in ("trade_id", "order_id"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    for col in ("price", "quantity", "amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    for col in ("fee", "profit"):
        if col in df.columns:
            df[col] = df[col].apply(parse_currency_value)

    df["direction"] = df["direction"].astype(str).str.lower().str.strip()

    if "amount" not in df.columns:
        df["amount"] = df["price"] * df["quantity"]

    if "timestamp" in df.columns:
        df = df.sort_values("timestamp", ascending=False)

    return df.reset_index(drop=True)


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

    if not Path(file_path).exists():
        return empty_trades()

    return normalize_trades(pd.read_excel(file_path))


def _format_euro(value) -> str:
    return f"€{value:.2f}" if pd.notna(value) and value else "€0"


def to_export_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert internal trades DataFrame into the Freedom Excel layout.

    Rows are sorted oldest-first *before* the timestamp is turned into text:
    sorting the "dd.mm.YYYY" strings would order them by day-of-month.
    """
    export_df = df.copy()

    if "timestamp" in export_df.columns:
        export_df["timestamp"] = pd.to_datetime(export_df["timestamp"])
        export_df = export_df.sort_values("timestamp", ascending=True)
        export_df["timestamp"] = export_df["timestamp"].dt.strftime(TIMESTAMP_FORMAT)

    for col in ("fee", "profit"):
        if col in export_df.columns:
            export_df[col] = export_df[col].apply(_format_euro)

    return export_df.rename(columns=EXPORT_HEADERS)


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
        to_export_frame(df).to_excel(file_path, index=False)
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
