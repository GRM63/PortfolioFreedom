"""
Historical market data from yfinance, with caching.
"""

import math
from typing import Optional

import pandas as pd
import streamlit as st
import yfinance as yf

from config import HISTORY_CACHE_TTL, QUOTE_CACHE_TTL


@st.cache_data(ttl=HISTORY_CACHE_TTL, show_spinner=False)
def get_price_history(ticker: str, period: str = "1mo") -> Optional[pd.DataFrame]:
    """
    Fetch historical OHLCV data for a ticker.

    Args:
        ticker: yfinance ticker symbol
        period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, ytd)

    Returns:
        DataFrame with OHLCV data, or None on error / no data
    """
    try:
        hist = yf.Ticker(ticker).history(period=period)
    except Exception as e:
        print(f"Error fetching history for {ticker}: {e}")
        return None

    return None if hist.empty else hist


def _first_number(info: dict, *keys: str) -> Optional[float]:
    """First of `keys` in `info` holding a positive, finite number."""
    for key in keys:
        value = info.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
            return float(value)
    return None


def compute_daily_change_pct(info: dict, hist: Optional[pd.DataFrame]) -> Optional[float]:
    """
    Today's % change versus the previous trading day's close.

    Prefers Yahoo's own quote fields (regularMarketPrice and
    regularMarketPreviousClose). Those come from Yahoo's quote service, so
    they stay correct when the daily history is missing a day; comparing the
    last two history rows would then measure a two-day move.

    Falls back to the last two closes in `hist` if the quote fields are absent.
    """
    price = _first_number(info, "regularMarketPrice", "currentPrice")
    prev = _first_number(info, "regularMarketPreviousClose", "previousClose")
    if price is not None and prev is not None:
        return (price / prev - 1) * 100

    if hist is not None and len(hist) >= 2:
        last, prev = hist["Close"].iloc[-1], hist["Close"].iloc[-2]
        if prev:
            return float((last / prev - 1) * 100)
    return None


@st.cache_data(ttl=QUOTE_CACHE_TTL, show_spinner=False)
def get_daily_change_pct(ticker: str) -> Optional[float]:
    """Fetch today's % change for `ticker` (see compute_daily_change_pct)."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as e:
        print(f"Error fetching quote for {ticker}: {e}")
        info = {}

    # Only download history when the quote didn't have what we need
    has_quote = (_first_number(info, "regularMarketPrice", "currentPrice") is not None
                 and _first_number(info, "regularMarketPreviousClose", "previousClose") is not None)
    hist = None if has_quote else get_price_history(ticker, "5d")
    return compute_daily_change_pct(info, hist)


if __name__ == "__main__":
    hist = get_price_history("VWCE.DE", "1mo")
    print(hist.tail() if hist is not None else "No data")
    print(f"VWCE.DE daily change: {get_daily_change_pct('VWCE.DE')}")
