from datetime import date

import polars as pl
import pytest

from builders import business_days, compound, levels_frame, quotas_frame
from fund_monitor.calc.benchmarks import attach_accruals, attach_level
from fund_monitor.calc.returns import (
    daily_returns,
    rolling_12m_returns,
    subtract_months,
    window_returns,
)

DAYS = business_days(date(2026, 1, 2), 5)
QUOTAS = compound(100.0, [0.02, -0.02, 0.03, -0.01])
CDI_DAILY = 0.05


def small_windows() -> pl.DataFrame:
    return window_returns(quotas_frame("A", DAYS, QUOTAS), levels_frame(DAYS, CDI_DAILY), as_of=DAYS[-1])


def test_daily_returns() -> None:
    returns = daily_returns(quotas_frame("A", DAYS, QUOTAS))["daily_return"].to_list()
    assert returns[0] is None
    assert returns[1:] == pytest.approx([0.02, -0.02, 0.03, -0.01])


def test_cdi_level_accrues_rates_of_prior_days() -> None:
    levels = levels_frame(DAYS, CDI_DAILY)
    probe = pl.DataFrame({"date": [DAYS[0], DAYS[2], date(2026, 1, 10)]})
    probe = attach_accruals(attach_level(probe, levels, "cdi", "date", "cdi"), levels, "date", "accruals")
    assert probe["cdi"].to_list() == pytest.approx([1.0, 1.0005**2, 1.0005**5])
    assert probe["accruals"].to_list() == [0, 2, 5]


def test_since_start_return_matches_hand_calculation() -> None:
    row = small_windows().filter(pl.col("window") == "since_start").row(0, named=True)
    assert row["fund_return"] == pytest.approx(1.02 * 0.98 * 1.03 * 0.99 - 1)
    assert row["cdi_return"] == pytest.approx(1.0005**4 - 1)
    assert row["business_days"] == 4
    assert row["excess_cdi"] == pytest.approx(0.01929212 - (1.0005**4 - 1))


def test_short_windows_are_not_annualized_nor_compared_as_pct_cdi() -> None:
    row = small_windows().filter(pl.col("window") == "since_start").row(0, named=True)
    assert row["fund_annualized"] is None
    assert row["pct_cdi"] is None


def test_window_without_full_history_is_empty() -> None:
    row = small_windows().filter(pl.col("window") == "mtd").row(0, named=True)
    assert row["has_history"] is False
    assert row["fund_return"] is None


def test_twelve_month_window_annualizes_over_business_days() -> None:
    days = business_days(date(2025, 1, 2), 300)
    quotas = compound(1.0, [0.0006] * 299)
    windows = window_returns(quotas_frame("B", days, quotas), levels_frame(days, CDI_DAILY), as_of=days[-1])
    row = windows.filter(pl.col("window") == "12m").row(0, named=True)
    steps = row["business_days"]
    assert row["base_date"] <= subtract_months(days[-1], 12)
    assert row["fund_return"] == pytest.approx(1.0006**steps - 1)
    assert row["fund_annualized"] == pytest.approx(1.0006**252 - 1)
    assert row["cdi_annualized"] == pytest.approx(1.0005**252 - 1)
    assert row["pct_cdi"] == pytest.approx((1.0006**steps - 1) / (1.0005**steps - 1))


def test_rolling_twelve_months_uses_quota_a_year_before() -> None:
    days = business_days(date(2025, 1, 2), 300)
    quotas = compound(1.0, [0.0006] * 299)
    rolling = rolling_12m_returns(quotas_frame("B", days, quotas), levels_frame(days, CDI_DAILY))
    last = rolling.row(-1, named=True)
    steps = days.index(last["end_date"]) - days.index(last["base_date"])
    assert last["fund_return"] == pytest.approx(1.0006**steps - 1)
    assert last["cdi_return"] == pytest.approx(1.0005**steps - 1)


def test_subtract_months_clamps_to_month_end() -> None:
    assert subtract_months(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert subtract_months(date(2026, 1, 15), 12) == date(2025, 1, 15)
