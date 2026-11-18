"""Tests for the daily-change calculation used by alerts."""

import pandas as pd
import pytest

from market_data import compute_daily_change_pct


def history(closes_by_date):
    return pd.DataFrame({"Close": list(closes_by_date.values())},
                        index=pd.to_datetime(list(closes_by_date)))


# Daily history with Tuesday 17 Nov missing, as Yahoo returned it
GAPPY = history({"2026-11-13": 170.0, "2026-11-16": 169.0, "2026-11-18": 166.0})


def test_quote_previous_close_wins_over_gappy_history():
    # Yahoo's quote says the 17 Nov close was 167.0, so today's move is small,
    # even though the last two history rows (16 vs 18 Nov) show -1.78%.
    info = {"regularMarketPrice": 166.0, "regularMarketPreviousClose": 167.0}
    assert compute_daily_change_pct(info, GAPPY) == pytest.approx(-0.5988, abs=1e-4)


def test_falls_back_to_last_two_closes_without_quote():
    assert compute_daily_change_pct({}, GAPPY) == pytest.approx(-1.7751, abs=1e-4)


def test_alternative_quote_keys():
    info = {"currentPrice": 102.0, "previousClose": 100.0}
    assert compute_daily_change_pct(info, None) == pytest.approx(2.0)


@pytest.mark.parametrize("info", [
    {"regularMarketPrice": 100.0},                                  # no previous close
    {"regularMarketPrice": 100.0, "regularMarketPreviousClose": 0},  # invalid
    {"regularMarketPrice": float("nan"), "regularMarketPreviousClose": 99.0},
    {"regularMarketPrice": "100", "regularMarketPreviousClose": 99.0},
])
def test_unusable_quote_uses_history(info):
    assert compute_daily_change_pct(info, GAPPY) == pytest.approx(-1.7751, abs=1e-4)


def test_no_data_at_all():
    assert compute_daily_change_pct({}, None) is None
    assert compute_daily_change_pct({}, history({"2026-11-18": 166.0})) is None
