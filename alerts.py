"""
Price alert system for portfolio monitoring.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import streamlit as st


class AlertType(Enum):
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    CHANGE_PCT_ABOVE = "change_pct_above"
    CHANGE_PCT_BELOW = "change_pct_below"


@dataclass
class Alert:
    ticker: str
    alert_type: AlertType
    threshold: float
    enabled: bool = True
    triggered: bool = False


def init_alerts():
    """Initialize alerts in session state if not present."""
    if "alerts" not in st.session_state:
        st.session_state.alerts = {}
    if "triggered_alerts" not in st.session_state:
        st.session_state.triggered_alerts = []
    if "alert_history" not in st.session_state:
        st.session_state.alert_history = []


def add_alert(ticker: str, alert_type: AlertType, threshold: float) -> str:
    """
    Add a new price alert.

    Returns:
        Alert ID
    """
    init_alerts()

    alert_id = f"{ticker}_{alert_type.value}_{threshold}"
    st.session_state.alerts[alert_id] = Alert(
        ticker=ticker,
        alert_type=alert_type,
        threshold=threshold,
        enabled=True,
        triggered=False
    )

    return alert_id


def remove_alert(alert_id: str):
    """Remove an alert by ID."""
    init_alerts()
    if alert_id in st.session_state.alerts:
        del st.session_state.alerts[alert_id]


def toggle_alert(alert_id: str, enabled: bool):
    """Enable or disable an alert."""
    init_alerts()
    if alert_id in st.session_state.alerts:
        st.session_state.alerts[alert_id].enabled = enabled


def get_alerts(ticker: Optional[str] = None) -> Dict[str, Alert]:
    """Get all alerts, optionally filtered by ticker."""
    init_alerts()
    if ticker is None:
        return st.session_state.alerts
    return {
        aid: alert for aid, alert in st.session_state.alerts.items()
        if alert.ticker == ticker
    }


def check_alerts(prices: Dict[str, dict]) -> List[Dict]:
    """
    Check all alerts against current prices.

    Args:
        prices: Dict of ticker -> price data from market_data.get_current_prices

    Returns:
        List of triggered alert notifications
    """
    init_alerts()
    triggered = []

    for alert_id, alert in st.session_state.alerts.items():
        if not alert.enabled:
            continue

        price_data = prices.get(alert.ticker)
        if price_data is None or price_data.get("price") is None:
            continue

        current_price = price_data["price"]
        change_pct = price_data.get("change_pct", 0)

        is_triggered = False
        message = ""

        if alert.alert_type == AlertType.PRICE_ABOVE:
            if current_price >= alert.threshold:
                is_triggered = True
                message = f"{alert.ticker} is above {alert.threshold:.2f} (current: {current_price:.2f})"

        elif alert.alert_type == AlertType.PRICE_BELOW:
            if current_price <= alert.threshold:
                is_triggered = True
                message = f"{alert.ticker} is below {alert.threshold:.2f} (current: {current_price:.2f})"

        elif alert.alert_type == AlertType.CHANGE_PCT_ABOVE:
            if change_pct >= alert.threshold:
                is_triggered = True
                message = f"{alert.ticker} up {change_pct:.2f}% (threshold: {alert.threshold:.2f}%)"

        elif alert.alert_type == AlertType.CHANGE_PCT_BELOW:
            if change_pct <= alert.threshold:
                is_triggered = True
                message = f"{alert.ticker} down {change_pct:.2f}% (threshold: {alert.threshold:.2f}%)"

        if is_triggered and not alert.triggered:
            alert.triggered = True
            notification = {
                "alert_id": alert_id,
                "ticker": alert.ticker,
                "type": alert.alert_type.value,
                "message": message,
                "price": current_price,
            }
            triggered.append(notification)
            st.session_state.alert_history.append(notification)

    st.session_state.triggered_alerts = triggered
    return triggered


def reset_triggered_status(alert_id: Optional[str] = None):
    """Reset triggered status for alert(s)."""
    init_alerts()
    if alert_id:
        if alert_id in st.session_state.alerts:
            st.session_state.alerts[alert_id].triggered = False
    else:
        for alert in st.session_state.alerts.values():
            alert.triggered = False


def clear_alert_history():
    """Clear the alert history."""
    init_alerts()
    st.session_state.alert_history = []


def get_alert_history() -> List[Dict]:
    """Get list of all triggered alerts."""
    init_alerts()
    return st.session_state.alert_history


def format_alert_type(alert_type: AlertType) -> str:
    """Get human-readable alert type description."""
    descriptions = {
        AlertType.PRICE_ABOVE: "Price rises above",
        AlertType.PRICE_BELOW: "Price falls below",
        AlertType.CHANGE_PCT_ABOVE: "Daily gain exceeds",
        AlertType.CHANGE_PCT_BELOW: "Daily loss exceeds",
    }
    return descriptions.get(alert_type, alert_type.value)
