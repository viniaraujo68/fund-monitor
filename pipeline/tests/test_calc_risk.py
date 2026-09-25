import math
import statistics
from datetime import date

import polars as pl
import pytest

from builders import business_days, compound, levels_frame, quotas_frame
from fund_monitor.calc import risk
from fund_monitor.calc.returns import daily_returns, window_returns

CDI_DAILY = 0.05


def test_volatility_drawdown_and_extremes_match_hand_calculation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(risk, "RISK_WINDOWS", ("since_start",))
    monkeypatch.setattr(risk, "MIN_OBSERVATIONS", 2)
    days = business_days(date(2026, 1, 2), 5)
    quotas = quotas_frame("A", days, compound(100.0, [0.02, -0.02, 0.03, -0.01]))
    levels = levels_frame(days, CDI_DAILY)
    windows = window_returns(quotas, levels, as_of=days[-1])
    row = risk.risk_metrics(quotas, daily_returns(quotas), levels, windows).row(0, named=True)
    deviations = [0.015, -0.025, 0.025, -0.015]
    assert row["volatility"] == pytest.approx(math.sqrt(sum(d * d for d in deviations) / 3) * math.sqrt(252))
    assert row["max_drawdown"] == pytest.approx(-0.02)
    assert (row["peak_date"], row["trough_date"], row["recovery_date"]) == (days[1], days[2], days[3])
    assert (row["best_day"], row["best_day_date"]) == (pytest.approx(0.03), days[3])
    assert (row["worst_day"], row["worst_day_date"]) == (pytest.approx(-0.02), days[2])
    assert row["positive_days_share"] == pytest.approx(0.5)
    assert row["sharpe"] is None


def test_drawdown_without_recovery() -> None:
    days = business_days(date(2026, 1, 2), 4)
    quotas = quotas_frame("A", days, [100.0, 110.0, 99.0, 104.5])
    windows = pl.DataFrame(
        {"series_id": ["A"], "window": ["12m"], "base_date": [days[0]], "end_date": [days[-1]], "fund_return": [0.045]}
    )
    row = risk.max_drawdown(quotas, windows).row(0, named=True)
    assert row["max_drawdown"] == pytest.approx(99.0 / 110.0 - 1)
    assert row["recovery_date"] is None


def test_sharpe_beta_and_tracking_error_over_twelve_months() -> None:
    days = business_days(date(2025, 1, 2), 300)
    market_returns = [0.004 if position % 2 else -0.002 for position in range(299)]
    ima_b = compound(1000.0, market_returns)
    fund_returns = [2 * r for r in market_returns]
    quotas = quotas_frame("RF", days, compound(10.0, fund_returns))
    levels = levels_frame(days, CDI_DAILY, ima_b=ima_b)
    windows = window_returns(quotas, levels, as_of=days[-1])
    metrics = risk.risk_metrics(quotas, daily_returns(quotas), levels, windows)
    row = metrics.filter(pl.col("window") == "12m").row(0, named=True)
    window = windows.filter(pl.col("window") == "12m").row(0, named=True)
    start = days.index(window["base_date"])
    in_window = fund_returns[start:]
    market_in_window = market_returns[start:]
    volatility = statistics.stdev(in_window) * math.sqrt(252)
    assert row["observations"] == len(in_window)
    assert row["volatility"] == pytest.approx(volatility, rel=1e-6)
    assert row["beta_ima_b"] == pytest.approx(2.0, rel=1e-6)
    assert row["tracking_error_ima_b"] == pytest.approx(statistics.stdev(market_in_window) * math.sqrt(252), rel=1e-6)
    expected_sharpe = (window["fund_annualized"] - window["cdi_annualized"]) / volatility
    assert row["sharpe"] == pytest.approx(expected_sharpe, rel=1e-6)
    assert row["beta_ibov"] is None


def test_too_few_observations_leave_risk_empty() -> None:
    days = business_days(date(2026, 1, 2), 30)
    quotas = quotas_frame("NEW", days, compound(1.0, [0.001, -0.001] * 14 + [0.001]))
    windows = pl.DataFrame(
        {"series_id": ["NEW"], "window": ["12m"], "base_date": [days[0]], "end_date": [days[-1]], "fund_return": [0.001]}
    )
    row = risk.return_statistics(daily_returns(quotas), levels_frame(days, CDI_DAILY), windows).row(0, named=True)
    assert row["observations"] == 29
    assert row["volatility"] is None
    assert row["positive_days_share"] is None


def test_drawdown_series_is_relative_to_running_peak() -> None:
    cumulative = pl.DataFrame(
        {"series_id": ["A"] * 4, "date": business_days(date(2026, 1, 2), 4), "fund_index": [100.0, 110.0, 99.0, 115.0]}
    )
    assert risk.drawdown_series(cumulative)["drawdown"].to_list() == pytest.approx([0.0, 0.0, 99.0 / 110.0 - 1, 0.0])
