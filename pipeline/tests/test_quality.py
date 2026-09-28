import statistics
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from builders import SAMPLE_DAYS, SAMPLE_ZEROED_DAY, business_days, compound, install_sources, sample_sources
from fund_monitor import config
from fund_monitor.calc.engine import calculate, write_metrics
from fund_monitor.calc.returns import daily_returns
from fund_monitor.calc.series import quota_series
from fund_monitor.quality import checks, report
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
        {"series_id": series_id, "date": days, "quota_value": [Decimal(f"{v:.12f}") for v in values], "inherited": False},
        schema={"series_id": pl.String, "date": pl.Date, "quota_value": pl.Decimal(28, 12), "inherited": pl.Boolean},
    )


def base_inputs(**overrides) -> QualityInputs:
    series = pl.DataFrame({"cnpj": [CNPJ], "subclass_id": [None], "cvm_classification": ["Renda Fixa"]}, schema_overrides={"subclass_id": pl.String})
    series_quotas = quotas(DAYS, [1.0] * len(DAYS))
    defaults = QualityInputs(
        raw_daily=daily_rows([{"date": day} for day in DAYS]),
        daily=daily_rows([{"date": day} for day in DAYS]),
        manager_series=series,
        manager_registry=series,
        monitored=series,
        quotas=series_quotas,
        returns=daily_returns(series_quotas),
        monthly_flows=pl.DataFrame(
            schema={"series_id": pl.String, "month": pl.Date, "last_report_date": pl.Date, "unexplained_share": pl.Float64}
        ),
        windows=pl.DataFrame(
            {"series_id": [CNPJ], "window": ["12m"], "first_date": [DAYS[0]], "fund_return": [0.1]}
        ),
        calendar=DAYS,
        market_jump_share=pl.DataFrame(
            schema={"date": pl.Date, "cvm_classification": pl.String, "market_share": pl.Float64}
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


def market_share_on(day: date, share: float) -> pl.DataFrame:
    return pl.DataFrame({"date": [day], "cvm_classification": ["Renda Fixa"], "market_share": [share]})


def jump_inputs(last_return: float, market_share: float | None = None) -> QualityInputs:
    days = business_days(date(2025, 11, 3), 72)
    values = compound(1.0, [0.0006, 0.0004] * 35 + [last_return])
    frame = quotas(days, values)
    return base_inputs(
        quotas=frame, returns=daily_returns(frame), calendar=days, market_jump_share=market_share_on(days[-1], market_share or 0.0)
    )


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
    assert found["threshold"].item() == checks.FIXED_INCOME_JUMP


def test_floor_driven_jump_publishes_the_floor() -> None:
    found = checks.quota_jumps(jump_inputs(-0.004))
    assert found["threshold"].item() == checks.MATERIAL_DEVIATION


def test_sigma_driven_jump_publishes_five_sigma() -> None:
    days = business_days(date(2025, 11, 3), 72)
    history = [0.01, -0.01] * 35
    frame = quotas(days, compound(1.0, [*history, 0.2]))
    monitored = pl.DataFrame({"cnpj": [CNPJ], "subclass_id": [None], "cvm_classification": ["Ações"]}, schema_overrides={"subclass_id": pl.String})
    found = checks.quota_jumps(base_inputs(quotas=frame, returns=daily_returns(frame), calendar=days, monitored=monitored))
    assert found.select("detail", "value").rows() == [("statistical", pytest.approx(0.2))]
    assert found["threshold"].item() == pytest.approx(checks.JUMP_SIGMAS * statistics.stdev(history[-60:]))


def di_inputs(last_return: float) -> QualityInputs:
    days = business_days(date(2025, 11, 3), 80)
    values = compound(1.0, [0.00056, 0.00054] * 39 + [last_return])
    kept = days[:70] + days[72:]
    frame = quotas(kept, values[:70] + values[72:])
    return base_inputs(quotas=frame, returns=daily_returns(frame), calendar=days, market_jump_share=market_share_on(days[-1], 0.0))


def test_return_across_a_reporting_gap_is_not_a_jump() -> None:
    assert checks.quota_jumps(di_inputs(0.00055)).is_empty()


def test_real_move_across_a_reporting_gap_is_still_a_jump() -> None:
    days = business_days(date(2025, 11, 3), 80)
    values = compound(1.0, [0.00056, 0.00054] * 35 + [-0.005] + [0.00055] * 8)
    kept = days[:69] + days[71:]
    frame = quotas(kept, values[:69] + values[71:])
    found = checks.quota_jumps(base_inputs(quotas=frame, returns=daily_returns(frame), calendar=days))
    assert found.select("date", "detail", "threshold").rows() == [(days[71], "statistical", checks.MATERIAL_DEVIATION)]


def test_market_share_counts_jumps_per_classification_and_day() -> None:
    days = business_days(date(2025, 11, 3), 72)
    frames = [quotas(days, compound(1.0, [0.0006, 0.0004] * 35 + [-0.01 if n == 0 else 0.0005]), series_id=f"S{n}") for n in range(10)]
    returns = daily_returns(pl.concat(frames)).with_columns(cvm_classification=pl.lit("Renda Fixa"))
    share = checks.market_jump_share(returns, days).sort("date")
    assert share.columns == ["date", "cvm_classification", "market_share"]
    assert share.filter(pl.col("date") == days[-1])["market_share"].item() == pytest.approx(0.1)
    assert share.filter(pl.col("date") < days[-1])["market_share"].sum() == 0


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


@pytest.mark.parametrize("reference_date", [date(2026, 9, 27), date(2026, 9, 28)])
def test_weekend_is_not_a_delay(reference_date: date) -> None:
    sources = {"cvm_daily": date(2026, 9, 24), "cdi": date(2026, 9, 25), "ima_b": date(2026, 9, 25), "ibov": date(2026, 9, 25)}
    found = checks.stale_sources(base_inputs(source_dates=sources, reference_date=reference_date))
    assert found.is_empty()
    assert found.columns == list(checks.ISSUE_SCHEMA)


def test_long_delay_is_high() -> None:
    sources = {"cvm_daily": date(2026, 9, 24), "cdi": date(2026, 9, 21), "ima_b": date(2026, 9, 18), "ibov": date(2026, 9, 25)}
    found = checks.stale_sources(base_inputs(source_dates=sources, reference_date=date(2026, 9, 28))).sort("detail")
    assert found.select("detail", "days", "severity").rows() == [("cdi", 4, "medium"), ("ima_b", 5, "high")]


def test_registry_mismatch_ignores_rows_before_split() -> None:
    subclass = pl.DataFrame({"cnpj": [CNPJ], "subclass_id": ["RETAIL"], "cvm_classification": ["Renda Fixa"]})
    raw = daily_rows(
        [
            {"date": DAYS[0]},
            {"date": DAYS[1], "subclass_id": "RETAIL"},
            {"date": DAYS[2], "subclass_id": "UNKNOWN"},
        ]
    )
    found = checks.registry_mismatches(base_inputs(raw_daily=raw, manager_series=subclass, manager_registry=subclass, monitored=subclass))
    assert found.select("date", "detail").rows() == [(DAYS[2], "reported but not registered")]


def test_class_monitored_as_itself_keeps_its_rows_after_subclass_rows_appear() -> None:
    raw = daily_rows([{"date": day} for day in DAYS[:6]] + [{"date": day, "subclass_id": "NEW"} for day in DAYS[6:]])
    found = checks.registry_mismatches(base_inputs(raw_daily=raw))
    assert found.select("series_id", "date", "detail").rows() == [(f"{CNPJ}-NEW", DAYS[6], "reported but not registered")]


def test_registered_but_inactive_series_is_not_called_unregistered() -> None:
    inactive = pl.DataFrame({"cnpj": [CNPJ, CNPJ], "subclass_id": [None, "NEW"], "cvm_classification": ["Renda Fixa"] * 2})
    raw = daily_rows([{"date": day} for day in DAYS[:6]] + [{"date": day, "subclass_id": "NEW"} for day in DAYS[6:]])
    found = checks.registry_mismatches(base_inputs(raw_daily=raw, manager_registry=inactive))
    assert found.select("series_id", "days", "detail").rows() == [(f"{CNPJ}-NEW", 2, "reported but not active")]


def test_registry_mismatch_flags_series_never_reported() -> None:
    other = pl.DataFrame({"cnpj": [CNPJ, "22222222000122"], "subclass_id": [None, None], "cvm_classification": ["Renda Fixa"] * 2}, schema_overrides={"subclass_id": pl.String})
    found = checks.registry_mismatches(base_inputs(manager_series=other, manager_registry=other, monitored=other))
    assert found.select("series_id", "detail").rows() == [("22222222000122", "registered but never reported")]


def test_run_checks_orders_by_severity() -> None:
    daily = daily_rows([{"date": DAYS[0], "shareholders": 0}])
    sources = {"cvm_daily": None, "cdi": date(2026, 9, 25), "ima_b": date(2026, 9, 25), "ibov": date(2026, 9, 25)}
    found = checks.run_checks(base_inputs(daily=daily, source_dates=sources))
    assert found["severity"].to_list() == sorted(found["severity"].to_list(), key=checks.SEVERITIES.index)
    assert found["severity"].to_list()[0] == "high"


def test_checked_days_count_each_series_from_its_first_report() -> None:
    frame = pl.concat([quotas(DAYS, [1.0] * 8), quotas(DAYS[3:], [1.0] * 5, series_id="LATE")])
    assert checks.checked_days(base_inputs(quotas=frame)) == 8 + 5


def test_class_rows_are_attached_to_a_subclass_only_while_it_inherits() -> None:
    heir = pl.DataFrame({"cnpj": [CNPJ], "subclass_id": ["RETAIL"], "cvm_classification": ["Renda Fixa"]})
    daily = daily_rows(
        [{"date": day} for day in DAYS[:3]] + [{"date": day, "subclass_id": "RETAIL"} for day in DAYS[3:]] + [{"date": DAYS[5]}]
    )
    attached = checks.attach_series(daily.filter(pl.col("subclass_id").is_null()), heir, quota_series(daily, heir))
    assert attached.select("series_id", "date").sort("date").rows() == [(f"{CNPJ}-RETAIL", day) for day in DAYS[:3]]


def test_class_rows_are_not_attached_to_a_subclass_that_does_not_inherit() -> None:
    heir = pl.DataFrame({"cnpj": [CNPJ], "subclass_id": ["LATE"], "cvm_classification": ["Renda Fixa"]})
    daily = daily_rows([{"date": DAYS[0]}, {"date": date(2026, 4, 1), "subclass_id": "LATE"}])
    assert checks.attach_series(daily.filter(pl.col("subclass_id").is_null()), heir, quota_series(daily, heir)).is_empty()


def test_quality_stage_reads_sources_up_to_the_complete_day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    daily, peer_daily, registry = sample_sources()
    install_sources(tmp_path, monkeypatch, daily, peer_daily, SAMPLE_DAYS)
    write_metrics(calculate(registry))
    inputs = report.build_inputs(registry, date(2026, 2, 27))
    assert inputs.as_of == SAMPLE_DAYS[-1]
    assert inputs.raw_daily["date"].max() == SAMPLE_DAYS[-1]
    assert inputs.calendar == SAMPLE_DAYS
    assert inputs.source_dates["cvm_daily"] == date(2026, 2, 26)
    assert checks.checked_days(inputs) == 2 * len(SAMPLE_DAYS)
    issues = report.run_quality(registry, date(2026, 2, 27))
    daily_rules = issues.filter(pl.col("series_id") == "A", pl.col("rule").is_in(["missing_report", "zero_values", "quota_jump"]))
    assert daily_rules.select("rule", "severity", "date").sort("rule").rows() == [
        ("missing_report", "low", SAMPLE_ZEROED_DAY),
        ("zero_values", "high", SAMPLE_ZEROED_DAY),
    ]
    for name in (report.ISSUES_METRIC, report.COVERAGE_METRIC, report.SOURCES_METRIC):
        assert (config.METRICS_DIR / f"{name}.parquet").exists()
    coverage = pl.read_parquet(config.METRICS_DIR / f"{report.COVERAGE_METRIC}.parquet").row(0, named=True)
    assert coverage == {"checked_series": 2, "checked_days": 2 * len(SAMPLE_DAYS)}
