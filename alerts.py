"""
Price alerts for portfolio monitoring.

Plain Python (no Streamlit), so the logic can be unit-tested. Alerts and the
trigger history are stored in a small JSON file, so they survive page
reloads and app restarts.

Lifecycle of an alert:
    armed (⏳) --condition met--> triggered (🔔) --user re-arms--> armed
A triggered alert doesn't fire again until it is re-armed, so it can't spam
a notification on every refresh.
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

ALERTS_FILE = "alerts.json"
MAX_HISTORY = 50


class AlertType(Enum):
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    CHANGE_PCT_ABOVE = "change_pct_above"
    CHANGE_PCT_BELOW = "change_pct_below"

    @property
    def needs_daily_change(self) -> bool:
        return self in (AlertType.CHANGE_PCT_ABOVE, AlertType.CHANGE_PCT_BELOW)


@dataclass
class Alert:
    ticker: str
    alert_type: AlertType
    threshold: float
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    triggered: bool = False
    triggered_at: Optional[str] = None


@dataclass
class AlertState:
    alerts: Dict[str, Alert] = field(default_factory=dict)
    history: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------- storage

def load_state(path: str = ALERTS_FILE) -> AlertState:
    """Load alerts and history; a missing or unreadable file means no alerts."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return AlertState()

    alerts = {}
    for item in raw.get("alerts", []):
        try:
            alert = Alert(**{**item, "alert_type": AlertType(item["alert_type"])})
        except (KeyError, TypeError, ValueError):
            continue  # skip a malformed entry rather than lose every alert
        alerts[alert.id] = alert
    return AlertState(alerts=alerts, history=raw.get("history", []))


def save_state(state: AlertState, path: str = ALERTS_FILE) -> None:
    """Write state atomically: write a temp file, then rename over the old one."""
    data = {
        "alerts": [{**asdict(a), "alert_type": a.alert_type.value} for a in state.alerts.values()],
        "history": state.history[-MAX_HISTORY:],
    }
    tmp = Path(f"{path}.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


# ------------------------------------------------------------- mutations

def add_alert(state: AlertState, ticker: str, alert_type: AlertType, threshold: float) -> Alert:
    alert = Alert(ticker=ticker, alert_type=alert_type, threshold=float(threshold))
    state.alerts[alert.id] = alert
    return alert


def remove_alert(state: AlertState, alert_id: str) -> None:
    state.alerts.pop(alert_id, None)


def rearm_alert(state: AlertState, alert_id: str) -> None:
    alert = state.alerts.get(alert_id)
    if alert:
        alert.triggered = False
        alert.triggered_at = None


# ------------------------------------------------------------- evaluation

def evaluate(alert: Alert, price: Optional[float], change_pct: Optional[float]) -> Optional[str]:
    """
    Return a message if the alert's condition is met, else None.

    For CHANGE_PCT_BELOW the threshold is the size of the loss, entered as a
    positive number: threshold 3 fires when the daily change is -3% or worse.
    """
    t = alert.threshold
    kind = alert.alert_type

    if kind == AlertType.PRICE_ABOVE and price is not None and price >= t:
        return f"{alert.ticker} rose to {price:,.2f} (alert: above {t:,.2f})"
    if kind == AlertType.PRICE_BELOW and price is not None and price <= t:
        return f"{alert.ticker} fell to {price:,.2f} (alert: below {t:,.2f})"
    if kind == AlertType.CHANGE_PCT_ABOVE and change_pct is not None and change_pct >= t:
        return f"{alert.ticker} is up {change_pct:+.2f}% today (alert: gain ≥ {t:.2f}%)"
    if kind == AlertType.CHANGE_PCT_BELOW and change_pct is not None and change_pct <= -abs(t):
        return f"{alert.ticker} is down {change_pct:+.2f}% today (alert: loss ≥ {abs(t):.2f}%)"
    return None


def check_alerts(state: AlertState, quotes: Dict[str, dict], now: Optional[datetime] = None) -> List[dict]:
    """
    Check every armed alert against `quotes`.

    Args:
        state: alerts to check; fired alerts are marked triggered in place
        quotes: ticker -> {"price": float | None, "change_pct": float | None}
        now: timestamp to record (defaults to datetime.now())

    Returns:
        Notifications for alerts that fired in this check (also appended to
        state.history). The caller is responsible for saving the state.
    """
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    fired = []

    for alert in state.alerts.values():
        if alert.triggered:
            continue
        quote = quotes.get(alert.ticker)
        if not quote:
            continue

        message = evaluate(alert, quote.get("price"), quote.get("change_pct"))
        if message:
            alert.triggered = True
            alert.triggered_at = stamp
            note = {"alert_id": alert.id, "ticker": alert.ticker, "message": message, "time": stamp}
            fired.append(note)
            state.history.append(note)

    return fired


def format_alert_type(alert_type: AlertType) -> str:
    """Human-readable alert type description."""
    return {
        AlertType.PRICE_ABOVE: "Price rises above",
        AlertType.PRICE_BELOW: "Price falls below",
        AlertType.CHANGE_PCT_ABOVE: "Daily gain exceeds (%)",
        AlertType.CHANGE_PCT_BELOW: "Daily loss exceeds (%)",
    }[alert_type]
