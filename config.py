"""
Configuration and ticker mappings for the Portfolio Monitor.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env next to this file. Existing environment variables win
# (override=False), matching the previous hand-written parser.
load_dotenv(Path(__file__).parent / ".env", override=False)

# Freedom24/Tradernet API credentials (from environment variables)
TRADERNET_LOGIN = os.environ.get("TRADERNET_LOGIN", "")
TRADERNET_PASSWORD = os.environ.get("TRADERNET_PASSWORD", "")

# Data source: "api" for live Tradernet API, "excel" for Excel file
DATA_SOURCE = os.environ.get("DATA_SOURCE", "api" if TRADERNET_LOGIN else "excel")

# Map Freedom platform tickers to yfinance symbols
TICKER_MAPPING = {
    "VWCE.EU": "VWCE.DE",    # Vanguard FTSE All-World UCITS ETF (Xetra)
    "EQQB.EU": "EQQB.DE",    # Invesco EQQQ NASDAQ-100 UCITS ETF (Xetra)
    "DGRE.EU": "DGRE.DE",    # WisdomTree Emerging Markets Equity Income (Xetra)
    "VAGF.EU": "VAGF.DE",    # Vanguard Global Aggregate Bond (Xetra)
    "NVD.EU": "NVD.DE",      # GraniteShares NVIDIA 3x (Xetra)
    "AMD.US": "AMD",          # AMD (NYSE)
    "HOOD.US": "HOOD",        # Robinhood (NASDAQ)
    "AETF.GR": "AETF.AT",    # Greek ETF (Athens)
}

# Default refresh interval in seconds
DEFAULT_REFRESH_INTERVAL = 60

# Available refresh intervals (label, seconds)
REFRESH_INTERVALS = [
    ("30 seconds", 30),
    ("1 minute", 60),
    ("2 minutes", 120),
    ("5 minutes", 300),
]

# Chart settings
CHART_PERIODS = {
    "1 Day": "1d",
    "5 Days": "5d",
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "1 Year": "1y",
    "Year to Date": "ytd",
}

# Cache TTLs, in seconds
HISTORY_CACHE_TTL = 300   # price history for charts
QUOTE_CACHE_TTL = 60      # live quote used for daily-change alerts

# Excel file path
PORTFOLIO_FILE = "Portfolio_22012026.xlsx"
