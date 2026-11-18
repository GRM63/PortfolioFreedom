"""
Tradernet REST API client for the Freedom24 platform.
Fetches the current portfolio.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import requests


@dataclass
class PortfolioPosition:
    """Represents a single portfolio position."""
    ticker: str
    quantity: float
    avg_price: float
    current_price: float
    current_value: float
    profit: float
    profit_pct: float
    currency: str


@dataclass
class PortfolioData:
    """Complete portfolio data from Tradernet."""
    positions: List[PortfolioPosition]
    total_value: float
    total_profit: float
    total_profit_pct: float
    currency: str
    timestamp: datetime


class TradernetClient:
    """
    Tradernet REST API client.

    Usage:
        client = TradernetClient(login="your_email", password="your_password")
        portfolio = client.get_portfolio_sync()
    """

    API_URL = "https://tradernet.com/api"

    def __init__(self, login: str, password: str):
        self.login = login
        self.password = password
        self._http: Optional[requests.Session] = None
        self._logged_in = False

    REQUEST_TIMEOUT = 10.0  # seconds; without a timeout a stalled request hangs the app

    def _login(self) -> bool:
        """Log in on the shared HTTP session. Returns True on success."""
        resp = self._http.post(
            f"{self.API_URL}/v1/login",
            json={"login": self.login, "password": self.password},
            timeout=self.REQUEST_TIMEOUT,
        )
        self._logged_in = resp.status_code == 200
        if not self._logged_in:
            print(f"Login failed: {resp.status_code}")
        return self._logged_in

    def get_portfolio_sync(self, timeout: Optional[float] = None) -> Optional[PortfolioData]:
        """
        Synchronously fetch portfolio data via the REST API.

        The HTTP session (and its login cookies) is kept on the client, so
        repeated calls reuse the connection and only log in again when the
        server rejects the session.
        """
        if timeout is not None:
            self.REQUEST_TIMEOUT = timeout

        if self._http is None:
            self._http = requests.Session()
            self._logged_in = False

        try:
            for attempt in range(2):
                if not self._logged_in and not self._login():
                    return None

                resp = self._http.post(
                    f"{self.API_URL}/v1/portfolio",
                    json={},
                    timeout=self.REQUEST_TIMEOUT,
                )
                if resp.status_code in (401, 403) and attempt == 0:
                    self._logged_in = False  # session expired: log in once more
                    continue
                if resp.status_code == 200:
                    return self._parse_portfolio(resp.json())
                print(f"Portfolio request failed: {resp.status_code}")
                return None

        except requests.RequestException as e:
            print(f"Error fetching portfolio: {e}")

        return None

    def _parse_portfolio(self, data: Dict) -> PortfolioData:
        """Parse portfolio response into PortfolioData object."""
        positions = []

        # Parse positions from response
        pos_list = data.get("positions", data.get("portfolio", []))

        for pos in pos_list:
            positions.append(PortfolioPosition(
                ticker=pos.get("ticker", pos.get("c", "")),
                quantity=float(pos.get("qty", pos.get("q", 0))),
                avg_price=float(pos.get("avg_price", pos.get("avgPrice", pos.get("ap", 0)))),
                current_price=float(pos.get("price", pos.get("ltp", pos.get("p", 0)))),
                current_value=float(pos.get("value", pos.get("mv", 0))),
                profit=float(pos.get("profit", pos.get("pl", 0))),
                profit_pct=float(pos.get("profit_pct", pos.get("plp", 0))),
                currency=pos.get("currency", pos.get("cur", "EUR")),
            ))

        total_value = sum(p.current_value for p in positions)
        total_profit = sum(p.profit for p in positions)
        total_entry = sum(p.avg_price * p.quantity for p in positions)
        total_profit_pct = (total_profit / total_entry * 100) if total_entry > 0 else 0

        return PortfolioData(
            positions=positions,
            total_value=total_value,
            total_profit=total_profit,
            total_profit_pct=total_profit_pct,
            currency="EUR",
            timestamp=datetime.now()
        )


def fetch_portfolio(login: str, password: str) -> Optional[PortfolioData]:
    """
    Simple function to fetch current portfolio data.

    Args:
        login: Freedom24 email/login
        password: Freedom24 password

    Returns:
        PortfolioData object or None on error
    """
    client = TradernetClient(login, password)
    return client.get_portfolio_sync()


if __name__ == "__main__":
    # Test the client
    import os

    login = os.environ.get("TRADERNET_LOGIN", "")
    password = os.environ.get("TRADERNET_PASSWORD", "")

    if login and password:
        print("Fetching portfolio...")
        portfolio = fetch_portfolio(login, password)
        if portfolio:
            print(f"Total value: {portfolio.total_value:.2f} {portfolio.currency}")
            print(f"Total P/L: {portfolio.total_profit:.2f} ({portfolio.total_profit_pct:.2f}%)")
            print("\nPositions:")
            for pos in portfolio.positions:
                print(f"  {pos.ticker}: {pos.quantity} @ {pos.current_price:.2f} = {pos.current_value:.2f}")
        else:
            print("Failed to fetch portfolio")
    else:
        print("Set TRADERNET_LOGIN and TRADERNET_PASSWORD environment variables")
