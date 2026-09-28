from dataclasses import replace
from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from builders import business_days, compound
from fund_monitor.quality import checks
from fund_monitor.quality.checks import QualityInputs

CNPJ = "11111111000111"
DAYS = business_days(date(2026, 3, 2), 8)

DAILY_SCHEMA = {
    "cnpj": pl.String,
    "subclass_id": pl.String,
    "date": pl.Date,
    "report_type": pl.String,
    "quota_value": pl.Decimal(28, 12),
    "net_assets": pl.Decimal(20, 2),
    "total_assets": pl.Decimal(20, 2),
    "inflows": pl.Decimal(20, 2),
    "outflows": pl.Decimal(20, 2),
    "shareholders": pl.Int64,
}


def daily_rows(rows: list[dict]) -> pl.DataFrame:
    defaults = {
        "cnpj": CNPJ,
        "subclass_id": None,
        "report_type": "CLASSES - FIF",
        "quota_value": Decimal("1"),
        "net_assets": Decimal("100"),
        "total_assets": Decimal("100"),
        "inflows": Decimal("0"),
        "outflows": Decimal("0"),
        "shareholders": 10,
    }
    return pl.DataFrame([{**defaults, **row} for row in rows], schema=DAILY_SCHEMA)


def quotas(days: list[date], values: list[float], series_id: str = CNPJ) -> pl.DataFrame:
    return pl.DataFrame(
        {"series_id": series_id, "date": days, "quota_value": [Decimal(f"{v:.12f}") for v in values]},
        schema={"series_id": pl.String, "date": pl.Date, "quota_value": pl.Decimal(28, 12)},
    )


def returns_of(frame: pl.DataFrame) -> pl.DataFrame:
    quota = pl.col("quota_value").cast(pl.Float64)
    return frame.sort("date").with_columns(daily_return=quota / quota.shift(1) - 1)


def base_inputs(**overrides) -> QualityInputs:
    series = pl.DataFrame({"cnpj": [CNPJ], "subclass_id": [None], "cvm_classification": ["Renda Fixa"]}, schema_overrides={"subclass_id": pl.String})
    series_quotas = quotas(DAYS, [1.0] * len(DAYS))
    defaults = QualityInputs(
        raw_daily=daily_rows([{"date": day} for day in DAYS]),
        daily=daily_rows([{"date": day} for day in DAYS]),
        manager_series=series,
        monitored=series,
        quotas=series_quotas,
        returns=returns_of(series_quotas),
        monthly_flows=pl.DataFrame(
            schema={"series_id": pl.String, "month": pl.Date, "last_report_date": pl.Date, "unexplained_share": pl.Float64}
        ),
        windows=pl.DataFrame(
            {"series_id": [CNPJ], "window": ["12m"], "first_date": [DAYS[0]], "fund_return": [0.1]}
        ),
        calendar=DAYS,
        market_jump_share=pl.DataFrame(
            schema={"date": pl.Date, "cvm_classification": pl.String, "market_share": pl.Float64, "market_series": pl.UInt32}
        ),
        source_dates={"cvm_daily": date(2026, 9, 24), "cdi": date(2026, 9, 25), "ima_b": date(2026, 9, 25), "ibov": date(2026, 9, 25)},
        as_of=DAYS[-1],
        reference_date=date(2026, 9, 26),
    )
    return replace(defaults, **overrides)


def test_missing_reports_group_consecutive_days() -> None:
    kept = [DAYS[0], DAYS[1], DAYS[4], DAYS[5], DAYS[6], DAYS[7]]
    found = checks.missing_reports(base_inputs(quotas=quotas(kept, [1.0] * len(kept))))
    assert found.select("date", "end_date", "days", "severity").rows() == [(DAYS[2], DAYS[3], 2, "low")]


def test_long_gap_is_medium() -> None:
    kept = [DAYS[0], DAYS[6], DAYS[7]]
    found = checks.missing_reports(base_inputs(quotas=quotas(kept, [1.0] * 3)))
    assert found.select("days", "severity").rows() == [(5, "medium")]


def jump_inputs(last_return: float, market_share: float | None = None) -> QualityInputs:
    days = business_days(date(2025, 11, 3), 72)
    values = compound(1.0, [0.0006, 0.0004] * 35 + [last_return])
    frame = quotas(days, values)
    market = pl.DataFrame(
        {"date": [days[-1]], "cvm_classification": ["Renda Fixa"], "market_share": [market_share or 0.0], "market_series": [100]},
        schema_overrides={"market_series": pl.UInt32},
    )
    return base_inputs(quotas=frame, returns=returns_of(frame), market_jump_share=market)


def test_isolated_material_jump_is_medium() -> None:
    found = checks.quota_jumps(jump_inputs(-0.004))
    assert found.select("severity", "detail").rows() == [("medium", "statistical")]
    assert found["value"].item() == pytest.approx(-0.004)


def test_market_wide_jump_is_info() -> None:
    found = checks.quota_jumps(jump_inputs(-0.004, market_share=0.25))
    assert found.select("severity", "detail").rows() == [("info", "statistical; market-wide")]


def test_immaterial_deviation_is_not_a_jump() -> None:
    assert checks.quota_jumps(jump_inputs(0.0012)).is_empty()


def test_absolute_fixed_income_jump() -> None:
    found = checks.quota_jumps(jump_inputs(0.05))
    assert found["detail"].item() == "absolute"


def test_repeated_quota_needs_three_reports() -> None:
    frame = quotas(DAYS[:6], [1.0, 1.1, 1.1, 1.1, 1.2, 1.2])
    found = checks.repeated_quotas(base_inputs(quotas=frame))
    assert found.select("date", "end_date", "days").rows() == [(DAYS[1], DAYS[3], 3)]


def test_unexplained_net_assets_above_one_percent() -> None:
    flows = pl.DataFrame(
        {"series_id": [CNPJ, CNPJ], "month": [date(2026, 2, 1), date(2026, 3, 1)], "last_report_date": [date(2026, 2, 27), date(2026, 3, 31)], "unexplained_share": [0.005, -0.02]}
    )
    found = checks.unexplained_net_assets(base_inputs(monthly_flows=flows))
    assert found.select("date", "value").rows() == [(date(2026, 3, 1), -0.02)]


def test_zero_values_name_the_fields() -> None:
    daily = daily_rows([{"date": DAYS[0]}, {"date": DAYS[1], "shareholders": 0, "net_assets": Decimal("0")}])
    found = checks.zero_values(base_inputs(daily=daily))
    assert found.select("date", "severity", "detail").rows() == [(DAYS[1], "high", "net_assets,shareholders")]


def test_short_history_is_info() -> None:
    windows = pl.DataFrame({"series_id": [CNPJ], "window": ["12m"], "first_date": [DAYS[0]], "fund_return": [None]}, schema_overrides={"fund_return": pl.Float64})
    found = checks.short_history(base_inputs(windows=windows))
    assert found.select("severity", "date").rows() == [("info", DAYS[0])]


def test_duplicate_report_flags_only_conflicting_values() -> None:
    raw = daily_rows(
        [
            {"date": DAYS[0], "report_type": "FI", "inflows": Decimal("9082.08")},
            {"date": DAYS[0], "inflows": Decimal("64743.05")},
            {"date": DAYS[1], "report_type": "FI"},
            {"date": DAYS[1]},
        ]
    )
    found = checks.duplicate_reports(base_inputs(raw_daily=raw))
    assert found.select("date", "detail").rows() == [(DAYS[0], "types: CLASSES - FIF, FI; differing: inflows")]


def test_stale_sources_count_weekdays() -> None:
    sources = {"cvm_daily": date(2026, 9, 22), "cdi": date(2026, 9, 25), "ima_b": date(2026, 9, 24), "ibov": None}
    found = checks.stale_sources(base_inputs(source_dates=sources)).sort("detail")
    assert found.select("detail", "days", "severity").rows() == [("cvm_daily", 3, "medium"), ("ibov", None, "high")]


def test_registry_mismatch_ignores_rows_before_split() -> None:
    subclass = pl.DataFrame({"cnpj": [CNPJ], "subclass_id": ["RETAIL"], "cvm_classification": ["Renda Fixa"]})
    raw = daily_rows(
        [
            {"date": DAYS[0]},
            {"date": DAYS[1], "subclass_id": "RETAIL"},
            {"date": DAYS[2], "subclass_id": "UNKNOWN"},
        ]
    )
    found = checks.registry_mismatches(base_inputs(raw_daily=raw, manager_series=subclass, monitored=subclass))
    assert found.select("date", "detail").rows() == [(DAYS[2], "reported but not registered")]


def test_registry_mismatch_flags_series_never_reported() -> None:
    other = pl.DataFrame({"cnpj": [CNPJ, "22222222000122"], "subclass_id": [None, None], "cvm_classification": ["Renda Fixa"] * 2}, schema_overrides={"subclass_id": pl.String})
    found = checks.registry_mismatches(base_inputs(manager_series=other, monitored=other))
    assert found.select("series_id", "detail").rows() == [("22222222000122", "registered but never reported")]


def test_run_checks_orders_by_severity() -> None:
    daily = daily_rows([{"date": DAYS[0], "shareholders": 0}])
    sources = {"cvm_daily": None, "cdi": date(2026, 9, 25), "ima_b": date(2026, 9, 25), "ibov": date(2026, 9, 25)}
    found = checks.run_checks(base_inputs(daily=daily, source_dates=sources))
    assert found["severity"].to_list() == sorted(found["severity"].to_list(), key=checks.SEVERITIES.index)
    assert found["severity"].to_list()[0] == "high"
