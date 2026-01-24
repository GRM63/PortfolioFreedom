"""
Market data fetching via yfinance with caching.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import streamlit as st
from config import TICKER_CURRENCIES, PRICE_CACHE_TTL, HISTORY_CACHE_TTL


@st.cache_data(ttl=PRICE_CACHE_TTL)
def get_current_prices(tickers: Tuple[str, ...]) -> Dict[str, dict]:
    """
    Fetch current prices for a list of tickers.

    Returns dict with ticker as key and dict containing:
    - price: Current/last price
    - change: Absolute change
    - change_pct: Percentage change
    - currency: Currency of the price
    - market_state: Market state (REGULAR, PRE, POST, CLOSED)
    """
    results = {}

    if not tickers:
        return results

    # Convert tuple back to list for yfinance
    ticker_list = list(tickers)

    try:
        # Fetch data for all tickers at once
        data = yf.download(
            ticker_list,
            period="2d",
            interval="1d",
            progress=False,
            group_by="ticker"
        )

        for ticker in ticker_list:
            try:
                if len(ticker_list) == 1:
                    ticker_data = data
                else:
                    ticker_data = data[ticker] if ticker in data.columns.get_level_values(0) else None

                if ticker_data is not None and not ticker_data.empty:
                    # Get latest close
                    latest = ticker_data["Close"].iloc[-1]
                    prev = ticker_data["Close"].iloc[-2] if len(ticker_data) > 1 else latest

                    change = latest - prev
                    change_pct = (change / prev * 100) if prev != 0 else 0

                    results[ticker] = {
                        "price": float(latest),
                        "change": float(change),
                        "change_pct": float(change_pct),
                        "currency": TICKER_CURRENCIES.get(ticker, "USD"),
                        "market_state": "REGULAR",
                    }
            except Exception as e:
                print(f"Error processing {ticker}: {e}")
                continue

    except Exception as e:
        print(f"Error fetching prices: {e}")

    # Fill in any missing tickers with individual requests
    for ticker in ticker_list:
        if ticker not in results:
            try:
                stock = yf.Ticker(ticker)
                info = stock.fast_info

                price = info.last_price if hasattr(info, "last_price") else None
                prev_close = info.previous_close if hasattr(info, "previous_close") else price

                if price is not None:
                    change = price - prev_close if prev_close else 0
                    change_pct = (change / prev_close * 100) if prev_close else 0

                    results[ticker] = {
                        "price": float(price),
                        "change": float(change),
                        "change_pct": float(change_pct),
                        "currency": TICKER_CURRENCIES.get(ticker, "USD"),
                        "market_state": "REGULAR",
                    }
            except Exception as e:
                print(f"Error fetching {ticker} individually: {e}")
                results[ticker] = {
                    "price": None,
                    "change": 0,
                    "change_pct": 0,
                    "currency": TICKER_CURRENCIES.get(ticker, "USD"),
                    "market_state": "ERROR",
                }

    return results


@st.cache_data(ttl=HISTORY_CACHE_TTL)
def get_price_history(ticker: str, period: str = "1mo") -> Optional[pd.DataFrame]:
    """
    Fetch historical price data for a ticker.

    Args:
        ticker: yfinance ticker symbol
        period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, ytd)

    Returns:
        DataFrame with OHLCV data or None on error
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)

        if hist.empty:
            return None

        return hist

    except Exception as e:
        print(f"Error fetching history for {ticker}: {e}")
        return None


@st.cache_data(ttl=HISTORY_CACHE_TTL)
def get_intraday_data(ticker: str) -> Optional[pd.DataFrame]:
    """
    Fetch intraday price data for sparkline charts.

    Returns DataFrame with 5-minute intervals for current day.
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d", interval="5m")

        if hist.empty:
            return None

        return hist

    except Exception as e:
        print(f"Error fetching intraday data for {ticker}: {e}")
        return None


def get_exchange_rate(from_currency: str, to_currency: str) -> float:
    """
    Get exchange rate between two currencies.

    Args:
        from_currency: Source currency (e.g., "USD")
        to_currency: Target currency (e.g., "EUR")

    Returns:
        Exchange rate (1 from_currency = X to_currency)
    """
    if from_currency == to_currency:
        return 1.0

    try:
        # yfinance uses format like "USDEUR=X"
        pair = f"{from_currency}{to_currency}=X"
        ticker = yf.Ticker(pair)
        rate = ticker.fast_info.last_price
        return float(rate) if rate else 1.0

    except Exception as e:
        print(f"Error fetching exchange rate {from_currency}/{to_currency}: {e}")
        return 1.0


@st.cache_data(ttl=PRICE_CACHE_TTL)
def get_usd_eur_rate() -> float:
    """Get current USD to EUR exchange rate."""
    return get_exchange_rate("USD", "EUR")


def calculate_portfolio_values(
    portfolio: pd.DataFrame,
    prices: Dict[str, dict],
    convert_to_eur: bool = True
) -> pd.DataFrame:
    """
    Calculate current values and P/L for portfolio holdings.

    Args:
        portfolio: DataFrame with portfolio holdings
        prices: Dict of current prices from get_current_prices
        convert_to_eur: Whether to convert USD holdings to EUR

    Returns:
        Portfolio DataFrame with added columns:
        - current_price: Current market price
        - current_value: Current total value
        - pnl: Profit/Loss amount
        - pnl_pct: Profit/Loss percentage
        - day_change: Daily change amount
        - day_change_pct: Daily change percentage
    """
    df = portfolio.copy()

    usd_eur_rate = get_usd_eur_rate() if convert_to_eur else 1.0

    current_prices = []
    current_values = []
    pnl_amounts = []
    pnl_pcts = []
    day_changes = []
    day_change_pcts = []

    for _, row in df.iterrows():
        yf_ticker = row["yf_ticker"]
        quantity = row["quantity"]
        entry_price = row["entry_price"]
        entry_value = row["entry_value"]

        price_data = prices.get(yf_ticker, {})
        price = price_data.get("price")
        currency = price_data.get("currency", "EUR")

        if price is not None:
            # Convert USD prices to EUR if needed
            if convert_to_eur and currency == "USD":
                price_eur = price * usd_eur_rate
            else:
                price_eur = price

            current_value = quantity * price_eur
            pnl = current_value - entry_value
            pnl_pct = (pnl / entry_value * 100) if entry_value > 0 else 0

            day_change = price_data.get("change", 0) * quantity
            if convert_to_eur and currency == "USD":
                day_change *= usd_eur_rate

            day_change_pct = price_data.get("change_pct", 0)

            current_prices.append(price_eur)
            current_values.append(current_value)
            pnl_amounts.append(pnl)
            pnl_pcts.append(pnl_pct)
            day_changes.append(day_change)
            day_change_pcts.append(day_change_pct)
        else:
            current_prices.append(None)
            current_values.append(entry_value)
            pnl_amounts.append(0)
            pnl_pcts.append(0)
            day_changes.append(0)
            day_change_pcts.append(0)

    df["current_price"] = current_prices
    df["current_value"] = current_values
    df["pnl"] = pnl_amounts
    df["pnl_pct"] = pnl_pcts
    df["day_change"] = day_changes
    df["day_change_pct"] = day_change_pcts

    return df


if __name__ == "__main__":
    # Test market data fetching
    test_tickers = ("VWCE.DE", "AMD", "HOOD")
    print("Fetching prices for:", test_tickers)
    prices = get_current_prices(test_tickers)
    for ticker, data in prices.items():
        print(f"{ticker}: {data}")

    print("\nFetching history for VWCE.DE:")
    hist = get_price_history("VWCE.DE", "1mo")
    if hist is not None:
        print(hist.tail())
