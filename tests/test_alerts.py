"""Tests for price alert evaluation and storage."""

from datetime import datetime

import pytest

from alerts import (
    AlertState,
    AlertType,
    add_alert,
    check_alerts,
    load_state,
    rearm_alert,
    remove_alert,
    save_state,
)


@pytest.mark.parametrize("kind, threshold, price, change, fires", [
    (AlertType.PRICE_ABOVE, 100, 100.0, None, True),
    (AlertType.PRICE_ABOVE, 100, 99.99, None, False),
    (AlertType.PRICE_BELOW, 100, 95.0, None, True),
    (AlertType.PRICE_BELOW, 100, 101.0, None, False),
    (AlertType.CHANGE_PCT_ABOVE, 2, None, 2.5, True),
    (AlertType.CHANGE_PCT_ABOVE, 2, None, 1.0, False),
    # Loss threshold is entered as a positive number: 3 means "-3% or worse".
    (AlertType.CHANGE_PCT_BELOW, 3, None, -3.5, True),
    (AlertType.CHANGE_PCT_BELOW, 3, None, -1.0, False),
    (AlertType.CHANGE_PCT_BELOW, 3, None, 1.0, False),   # old code fired on this
    # Missing data never fires
    (AlertType.PRICE_ABOVE, 100, None, 5.0, False),
    (AlertType.CHANGE_PCT_ABOVE, 2, 200.0, None, False),
])
def test_conditions(kind, threshold, price, change, fires):
    state = AlertState()
    add_alert(state, "AMD.US", kind, threshold)
    fired = check_alerts(state, {"AMD.US": {"price": price, "change_pct": change}})
    assert bool(fired) is fires


def test_fires_once_until_rearmed():
    state = AlertState()
    alert = add_alert(state, "AMD.US", AlertType.PRICE_ABOVE, 100)
    quotes = {"AMD.US": {"price": 120.0, "change_pct": None}}

    assert len(check_alerts(state, quotes, now=datetime(2026, 1, 5, 10, 0))) == 1
    assert alert.triggered and alert.triggered_at == "2026-01-05T10:00:00"
    assert check_alerts(state, quotes) == []          # no repeat while triggered

    rearm_alert(state, alert.id)
    assert not alert.triggered
    assert len(check_alerts(state, quotes)) == 1
    assert len(state.history) == 2


def test_only_matching_ticker_fires():
    state = AlertState()
    add_alert(state, "AMD.US", AlertType.PRICE_ABOVE, 100)
    assert check_alerts(state, {"HOOD.US": {"price": 500.0}}) == []


def test_save_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "alerts.json")
    state = AlertState()
    a = add_alert(state, "AMD.US", AlertType.CHANGE_PCT_BELOW, 3)
    b = add_alert(state, "VWCE.EU", AlertType.PRICE_ABOVE, 150)
    check_alerts(state, {"VWCE.EU": {"price": 151.0}})
    save_state(state, path)

    loaded = load_state(path)
    assert set(loaded.alerts) == {a.id, b.id}
    assert loaded.alerts[a.id].alert_type is AlertType.CHANGE_PCT_BELOW
    assert loaded.alerts[b.id].triggered
    assert len(loaded.history) == 1

    remove_alert(loaded, a.id)
    save_state(loaded, path)
    assert set(load_state(path).alerts) == {b.id}


def test_missing_or_corrupt_file_gives_empty_state(tmp_path):
    assert load_state(str(tmp_path / "nope.json")).alerts == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert load_state(str(bad)).alerts == {}
