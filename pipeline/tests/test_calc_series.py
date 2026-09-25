from datetime import date
from decimal import Decimal

import polars as pl

from fund_monitor.calc.series import aggregate_rows, deduplicate_reports, quota_series

CNPJ = "44917374000141"
DAYS = [date(2025, 6, 12), date(2025, 6, 13), date(2025, 6, 16), date(2025, 6, 17), date(2025, 6, 18)]


def daily_row(subclass_id: str | None, day: date, quota: str, net_assets: str, report_type: str = "CLASSES - FIF") -> dict:
    return {
        "cnpj": CNPJ,
        "subclass_id": subclass_id,
        "date": day,
        "report_type": report_type,
        "quota_value": Decimal(quota),
        "net_assets": Decimal(net_assets),
        "total_assets": Decimal(net_assets),
        "inflows": Decimal("0"),
        "outflows": Decimal("0"),
        "shareholders": 10,
    }


def split_daily() -> pl.DataFrame:
    rows = [
        daily_row(None, DAYS[0], "1.0", "300"),
        daily_row(None, DAYS[1], "1.1", "330"),
        daily_row(None, DAYS[2], "1.2", "360"),
        daily_row("RETAIL", DAYS[3], "1.3", "260"),
        daily_row("PRIVATE", DAYS[3], "1.3", "130"),
        daily_row("RETAIL", DAYS[4], "1.4", "280"),
        daily_row("PRIVATE", DAYS[4], "1.4", "140"),
    ]
    return pl.DataFrame(rows, schema_overrides={"quota_value": pl.Decimal(28, 12), "net_assets": pl.Decimal(20, 2)})


def series(*subclass_ids: str) -> pl.DataFrame:
    return pl.DataFrame({"cnpj": [CNPJ] * len(subclass_ids), "subclass_id": list(subclass_ids)})


def test_subclass_inherits_class_quota_before_its_first_report() -> None:
    quotas = quota_series(split_daily(), series("RETAIL", "PRIVATE"))
    retail = quotas.filter(pl.col("series_id") == f"{CNPJ}-RETAIL")
    assert retail["date"].to_list() == DAYS
    assert retail["inherited"].to_list() == [True, True, True, False, False]
    assert [float(q) for q in retail["quota_value"]] == [1.0, 1.1, 1.2, 1.3, 1.4]


def test_subclass_created_after_class_stopped_reporting_does_not_inherit() -> None:
    late = daily_row("LATE", date(2025, 8, 12), "1.6", "50")
    daily = pl.concat([split_daily(), pl.DataFrame([late], schema=split_daily().schema)])
    quotas = quota_series(daily, series("RETAIL", "LATE"))
    assert quotas.filter(pl.col("series_id") == f"{CNPJ}-LATE")["date"].to_list() == [date(2025, 8, 12)]
    assert quotas.filter(pl.col("series_id") == f"{CNPJ}-RETAIL")["inherited"].sum() == 3


def test_invalid_quota_is_dropped() -> None:
    daily = pl.concat([split_daily(), pl.DataFrame([daily_row("RETAIL", date(2025, 6, 19), "0", "0")], schema=split_daily().schema)])
    quotas = quota_series(daily, series("RETAIL"))
    assert date(2025, 6, 19) not in quotas["date"].to_list()


def test_aggregate_counts_class_rows_once_before_split() -> None:
    rows = aggregate_rows(split_daily(), series("RETAIL", "PRIVATE"))
    totals = rows.group_by("date").agg(pl.col("net_assets").sum()).sort("date")
    assert [float(v) for v in totals["net_assets"]] == [300, 330, 360, 390, 420]


def test_aggregate_without_excluded_subclass_after_split() -> None:
    rows = aggregate_rows(split_daily(), series("RETAIL"))
    totals = rows.group_by("date").agg(pl.col("net_assets").sum()).sort("date")
    assert [float(v) for v in totals["net_assets"]] == [300, 330, 360, 260, 280]


def test_new_regime_report_wins_over_legacy_on_same_day() -> None:
    legacy = daily_row(None, DAYS[0], "1.0", "999", report_type="FI")
    daily = pl.concat([pl.DataFrame([legacy], schema=split_daily().schema), split_daily()])
    deduplicated = deduplicate_reports(daily)
    first_day = deduplicated.filter(pl.col("date") == DAYS[0])
    assert first_day.height == 1
    assert first_day["report_type"].item() == "CLASSES - FIF"
    assert float(first_day["net_assets"].item()) == 300
