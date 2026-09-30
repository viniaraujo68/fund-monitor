from datetime import date, timedelta
from decimal import Decimal

import polars as pl
import pytest

from builders import business_days, compound, levels_frame, quotas_frame
from fund_monitor.calc.benchmarks import attach_accruals, attach_level, benchmark_levels
from fund_monitor.calc.peers import peer_table
from fund_monitor.calc.returns import (
    cumulative_index,
    daily_returns,
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
    fund_return = 1.02 * 0.98 * 1.03 * 0.99 - 1
    assert row["fund_return"] == pytest.approx(fund_return)
    assert row["cdi_return"] == pytest.approx(1.0005**4 - 1)
    assert row["business_days"] == 4
    assert row["excess_cdi"] == pytest.approx(fund_return - (1.0005**4 - 1))


def test_each_anbima_index_is_its_own_benchmark() -> None:
    cdi = levels_frame(DAYS, CDI_DAILY).filter(pl.col("benchmark") == "cdi")
    indices = pl.DataFrame(
        {"index": "cdi", "date": DAYS, "value": [Decimal(str(CDI_DAILY))] * len(DAYS), "unit": "percent_per_day"},
        schema_overrides={"value": pl.Decimal(18, 8)},
    )
    ima = pl.DataFrame(
        {
            "index": ["IMA-B"] * len(DAYS) + ["IMA-B 5"] * len(DAYS),
            "date": DAYS + DAYS,
            "value": [100.0, 101.0, 102.0, 103.0, 104.0] + [100.0, 100.5, 101.0, 101.5, 102.0],
        }
    )
    empty = pl.DataFrame(schema={"index": pl.String, "date": pl.Date, "value": pl.Float64})
    levels = benchmark_levels(indices, ima, empty, empty)
    assert levels.filter(pl.col("benchmark") == "cdi").equals(cdi)
    row = window_returns(quotas_frame("A", DAYS, QUOTAS), levels, as_of=DAYS[-1]).filter(pl.col("window") == "since_start").row(0, named=True)
    assert row["ima_b_return"] == pytest.approx(0.04)
    assert row["ima_b_5_return"] == pytest.approx(0.02)
    assert row["excess_ima_b_5"] == pytest.approx(row["fund_return"] - 0.02)
    assert row["irf_m_return"] is None


def test_short_windows_are_not_annualized_but_have_pct_cdi() -> None:
    row = small_windows().filter(pl.col("window") == "since_start").row(0, named=True)
    assert row["fund_annualized"] is None
    assert row["pct_cdi"] == pytest.approx((1.02 * 0.98 * 1.03 * 0.99 - 1) / (1.0005**4 - 1))


def test_window_without_full_history_is_empty() -> None:
    row = small_windows().filter(pl.col("window") == "mtd").row(0, named=True)
    assert row["has_history"] is False
    assert row["fund_return"] is None


def test_twelve_month_window_annualizes_over_business_days() -> None:
    days = business_days(date(2025, 1, 2), 300)
    quotas = compound(1.0, [0.0006] * 299)
    windows = window_returns(quotas_frame("B", days, quotas), levels_frame(days, CDI_DAILY), as_of=days[-1])
    row = windows.filter(pl.col("window") == "12m").row(0, named=True)
    steps = days.index(days[-1]) - days.index(date(2025, 2, 25))
    assert (row["base_date"], row["end_date"]) == (date(2025, 2, 25), date(2026, 2, 25))
    assert row["business_days"] == steps
    assert row["fund_return"] == pytest.approx(1.0006**steps - 1)
    assert row["fund_annualized"] == pytest.approx(1.0006**252 - 1)
    assert row["cdi_annualized"] == pytest.approx(1.0005**252 - 1)
    assert row["pct_cdi"] == pytest.approx((1.0006**steps - 1) / (1.0005**steps - 1))


def test_subtract_months_clamps_to_month_end() -> None:
    assert subtract_months(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert subtract_months(date(2026, 1, 15), 12) == date(2025, 1, 15)


def test_level_and_day_count_expire_after_seven_days() -> None:
    levels = levels_frame(DAYS, CDI_DAILY)
    last_level = date(2026, 1, 9)
    probe = pl.DataFrame({"date": [last_level + timedelta(days=7), last_level + timedelta(days=8)]})
    probe = attach_accruals(attach_level(probe, levels, "cdi", "date", "cdi"), levels, "date", "accruals")
    assert probe["cdi"].to_list() == [pytest.approx(1.0005**5), None]
    assert probe["accruals"].to_list() == [5, None]


def test_stale_cdi_leaves_annualized_return_empty() -> None:
    days = business_days(date(2025, 1, 2), 300)
    quotas = compound(1.0, [0.0006] * 299)
    windows = window_returns(quotas_frame("B", days, quotas), levels_frame(days[:-10], CDI_DAILY), as_of=days[-1])
    row = windows.filter(pl.col("window") == "12m").row(0, named=True)
    assert row["business_days"] is None
    assert row["cdi_return"] is None
    assert row["fund_annualized"] is None


def quota_on(day: date) -> float:
    return 1 + (day - date(2024, 1, 1)).days / 1000


def dated_windows(as_of: date) -> pl.DataFrame:
    days = [day for day in business_days(date(2024, 1, 1), 700) if day <= as_of]
    quotas = quotas_frame("D", days, [quota_on(day) for day in days])
    return window_returns(quotas, levels_frame(days, CDI_DAILY), as_of=as_of)


def test_window_anchors_at_a_month_end() -> None:
    as_of = date(2026, 3, 31)
    rows = {row["window"]: row for row in dated_windows(as_of).iter_rows(named=True)}
    expected_bases = {
        "mtd": date(2026, 2, 27),
        "ytd": date(2025, 12, 31),
        "3m": date(2025, 12, 31),
        "6m": date(2025, 9, 30),
        "12m": date(2025, 3, 31),
        "24m": date(2024, 3, 29),
    }
    for window, base in expected_bases.items():
        assert rows[window]["base_date"] == base, window
        assert rows[window]["fund_return"] == pytest.approx(quota_on(as_of) / quota_on(base) - 1), window


def test_january_year_to_date_starts_on_the_last_day_of_the_previous_year() -> None:
    rows = {row["window"]: row for row in dated_windows(date(2026, 1, 15)).iter_rows(named=True)}
    assert rows["ytd"]["base_date"] == rows["mtd"]["base_date"] == date(2025, 12, 31)
    assert rows["ytd"]["fund_return"] == pytest.approx(quota_on(date(2026, 1, 15)) / quota_on(date(2025, 12, 31)) - 1)


def test_since_start_is_annualized_from_252_business_days() -> None:
    days = business_days(date(2025, 1, 2), 300)
    quotas = compound(1.0, [0.0006] * 299)
    windows = window_returns(quotas_frame("B", days, quotas), levels_frame(days, CDI_DAILY), as_of=days[-1])
    row = windows.filter(pl.col("window") == "since_start").row(0, named=True)
    assert row["business_days"] == 299
    assert row["fund_annualized"] == pytest.approx(1.0006**252 - 1)
    assert row["pct_cdi"] == pytest.approx((1.0006**299 - 1) / (1.0005**299 - 1))


def test_since_start_below_252_business_days_is_not_annualized() -> None:
    days = business_days(date(2025, 1, 2), 252)
    quotas = compound(1.0, [0.0006] * 251)
    windows = window_returns(quotas_frame("B", days, quotas), levels_frame(days, CDI_DAILY), as_of=days[-1])
    row = windows.filter(pl.col("window") == "since_start").row(0, named=True)
    assert row["business_days"] == 251
    assert row["fund_annualized"] is None
    assert row["pct_cdi"] == pytest.approx((1.0006**251 - 1) / (1.0005**251 - 1))


def stopped_series(cnpj: str) -> tuple[list[date], pl.DataFrame]:
    days = business_days(date(2025, 1, 2), 400)
    stopped = [day for day in days if day <= date(2026, 4, 8)]
    return days, quotas_frame(cnpj, stopped, compound(1.0, [0.0006] * (len(stopped) - 1)))


def test_series_that_stopped_reporting_is_not_annualized() -> None:
    days, quotas = stopped_series("OLD")
    windows = window_returns(quotas, levels_frame(days, CDI_DAILY), as_of=days[-1])
    row = windows.filter(pl.col("window") == "12m").row(0, named=True)
    assert row["end_date"] == date(2026, 4, 8)
    assert row["stale"] is True
    assert row["fund_annualized"] is None
    assert row["pct_cdi"] is None


def test_series_reporting_within_a_week_is_not_stale() -> None:
    days = business_days(date(2025, 1, 2), 300)
    quotas = quotas_frame("B", days[:-5], compound(1.0, [0.0006] * 294))
    row = window_returns(quotas, levels_frame(days, CDI_DAILY), as_of=days[-1]).filter(pl.col("window") == "12m").row(0, named=True)
    assert row["end_date"] == days[-6]
    assert row["stale"] is False
    assert row["fund_annualized"] is not None


def test_series_that_stopped_reporting_is_not_an_eligible_peer() -> None:
    days, quotas = stopped_series("OLD")
    daily = quotas.select(
        "cnpj",
        "subclass_id",
        "date",
        pl.lit("CLASSES - FIF").alias("report_type"),
        "quota_value",
        pl.lit(Decimal("100000000"), dtype=pl.Decimal(20, 2)).alias("net_assets"),
    )
    candidates = pl.DataFrame(
        {"cnpj": ["OLD"], "subclass_id": [None], "class_name": ["Old"], "anbima_classification": ["RF"], "target_audience": ["Público Geral"]},
        schema_overrides={"subclass_id": pl.String},
    )
    table = peer_table(daily, candidates, levels_frame(days, CDI_DAILY), as_of=days[-1])
    assert table["fund_return"].item() is not None
    assert table["eligible"].item() is False


def test_cumulative_index_rebases_fund_and_benchmarks_to_100() -> None:
    days = business_days(date(2026, 1, 5), 10)
    ima_b = [1000.0 + 10 * position for position in range(10)]
    levels = levels_frame(days, CDI_DAILY, ima_b=ima_b)
    quotas = pl.concat(
        [
            quotas_frame("EARLY", days, [2.0 + 0.1 * position for position in range(10)]),
            quotas_frame("LATE", days[5:], [5.0, 5.5, 6.0, 6.5, 7.0]),
        ]
    )
    index = cumulative_index(quotas, levels, start=days[2])
    early = index.filter(pl.col("series_id") == "EARLY")
    assert early["date"].to_list() == days[2:]
    assert early["fund_index"].to_list() == pytest.approx([100 * (2.0 + 0.1 * p) / 2.2 for p in range(2, 10)])
    assert early["ima_b_index"].to_list() == pytest.approx([100 * ima_b[p] / ima_b[2] for p in range(2, 10)])
    assert early["cdi_index"].to_list() == pytest.approx([100 * 1.0005 ** (p - 2) for p in range(2, 10)])
    late = index.filter(pl.col("series_id") == "LATE")
    assert late["date"].to_list() == days[5:]
    assert late["fund_index"].to_list() == pytest.approx([100.0, 110.0, 120.0, 130.0, 140.0])
    assert late["ima_b_index"][0] == pytest.approx(100.0)
