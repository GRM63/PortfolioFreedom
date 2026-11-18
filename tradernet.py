"""
Tradernet API client for Freedom24 platform.
Fetches live portfolio data and quotes via WebSocket.
"""

import json
import hashlib
import asyncio
import aiohttp
from typing import Optional, Callable, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime
import threading
import queue


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


class TrdernetClient:
    """
    Tradernet WebSocket API client.

    Usage:
        client = TradernetClient(login="your_email", password="your_password")
        portfolio = client.get_portfolio()
    """

    WS_URL = "wss://wss.tradernet.com"
    API_URL = "https://tradernet.com/api"

    def __init__(self, login: str, password: str):
        self.login = login
        self.password = password
        self._session_id: Optional[str] = None
        self._portfolio_data: Optional[Dict] = None
        self._quotes: Dict[str, Dict] = {}
        self._connected = False
        self._ws = None
        self._loop = None
        self._thread = None
        self._data_queue = queue.Queue()

    def _hash_password(self, password: str) -> str:
        """Hash password for authentication."""
        return hashlib.md5(password.encode()).hexdigest()

    async def _authenticate(self, session: aiohttp.ClientSession) -> Optional[str]:
        """Authenticate and get session ID."""
        auth_data = {
            "cmd": "login",
            "data": {
                "login": self.login,
                "password": self._hash_password(self.password),
                "version": "3.0"
            }
        }

        try:
            async with session.post(
                f"{self.API_URL}/v1/login",
                json={"login": self.login, "password": self.password}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("sessionId") or data.get("sid")
        except Exception as e:
            print(f"Auth error: {e}")

        return None

    async def _connect_websocket(self):
        """Connect to WebSocket and handle messages."""
        async with aiohttp.ClientSession() as session:
            # First authenticate via REST API
            # Then connect WebSocket with session
            async with session.ws_connect(self.WS_URL) as ws:
                self._ws = ws
                self._connected = True

                # Send auth message
                auth_msg = {
                    "cmd": "login",
                    "data": {
                        "login": self.login,
                        "password": self._hash_password(self.password)
                    }
                }
                await ws.send_json(auth_msg)

                # Handle incoming messages
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        self._handle_message(data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        break

        self._connected = False

    def _handle_message(self, data: Dict):
        """Handle incoming WebSocket message."""
        cmd = data.get("cmd")

        if cmd == "portfolio":
            self._portfolio_data = data.get("data", {})
            self._data_queue.put(("portfolio", self._portfolio_data))

        elif cmd == "q":  # Quote update
            quotes = data.get("data", [])
            for quote in quotes:
                ticker = quote.get("c")  # ticker code
                if ticker:
                    self._quotes[ticker] = quote
            self._data_queue.put(("quotes", self._quotes.copy()))

        elif cmd == "login":
            # Auth response
            if data.get("data", {}).get("result") == "ok":
                self._session_id = data.get("data", {}).get("sessionId")

    async def _subscribe_portfolio(self):
        """Subscribe to portfolio updates."""
        if self._ws and self._connected:
            await self._ws.send_json({
                "cmd": "subscribePortfolio",
                "data": {}
            })

    async def _subscribe_quotes(self, tickers: List[str]):
        """Subscribe to quote updates for given tickers."""
        if self._ws and self._connected:
            await self._ws.send_json({
                "cmd": "subscribeQuotes",
                "data": {"tickers": tickers}
            })

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
        import requests

        if timeout is not None:
            self.REQUEST_TIMEOUT = timeout

        if getattr(self, "_http", None) is None:
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


class TradernetStreamClient:
    """
    Streaming client for real-time portfolio and quote updates.
    Uses WebSocket connection for live data.
    """

    WS_URL = "wss://wss.tradernet.com"

    def __init__(self, login: str, password: str):
        self.login = login
        self.password = password
        self._callbacks: Dict[str, List[Callable]] = {
            "portfolio": [],
            "quotes": [],
            "connected": [],
            "error": [],
        }
        self._running = False
        self._task = None

    def on_portfolio(self, callback: Callable[[Dict], None]):
        """Register callback for portfolio updates."""
        self._callbacks["portfolio"].append(callback)

    def on_quotes(self, callback: Callable[[Dict], None]):
        """Register callback for quote updates."""
        self._callbacks["quotes"].append(callback)

    def on_connected(self, callback: Callable[[], None]):
        """Register callback for connection established."""
        self._callbacks["connected"].append(callback)

    def on_error(self, callback: Callable[[Exception], None]):
        """Register callback for errors."""
        self._callbacks["error"].append(callback)

    def _emit(self, event: str, data: Any = None):
        """Emit event to registered callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                if data is not None:
                    callback(data)
                else:
                    callback()
            except Exception as e:
                print(f"Callback error: {e}")

    async def _run(self, subscribe_tickers: Optional[List[str]] = None):
        """Main WebSocket connection loop."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(self.WS_URL) as ws:
                    # Authenticate
                    await ws.send_json({
                        "cmd": "login",
                        "data": {
                            "login": self.login,
                            "password": hashlib.md5(self.password.encode()).hexdigest()
                        }
                    })

                    # Wait for auth response then subscribe
                    auth_received = False

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            cmd = data.get("cmd")

                            if cmd == "login" and not auth_received:
                                auth_received = True
                                self._emit("connected")

                                # Subscribe to portfolio
                                await ws.send_json({"cmd": "subscribePortfolio"})

                                # Subscribe to quotes if tickers provided
                                if subscribe_tickers:
                                    await ws.send_json({
                                        "cmd": "subscribeQuotes",
                                        "data": {"tickers": subscribe_tickers}
                                    })

                            elif cmd == "portfolio":
                                self._emit("portfolio", data.get("data"))

                            elif cmd == "q":
                                self._emit("quotes", data.get("data"))

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            self._emit("error", Exception("WebSocket error"))
                            break

            except Exception as e:
                self._emit("error", e)

    def start(self, subscribe_tickers: Optional[List[str]] = None):
        """Start the streaming client in background."""
        self._running = True
        loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._run(subscribe_tickers))

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

    def stop(self):
        """Stop the streaming client."""
        self._running = False


def fetch_portfolio(login: str, password: str) -> Optional[PortfolioData]:
    """
    Simple function to fetch current portfolio data.

    Args:
        login: Freedom24 email/login
        password: Freedom24 password

    Returns:
        PortfolioData object or None on error
    """
    client = TrdernetClient(login, password)
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
