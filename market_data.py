"""
Historical market data from yfinance, with caching.
"""

from typing import Optional

import pandas as pd
import streamlit as st
import yfinance as yf

from config import HISTORY_CACHE_TTL


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


if __name__ == "__main__":
    hist = get_price_history("VWCE.DE", "1mo")
    print(hist.tail() if hist is not None else "No data")
