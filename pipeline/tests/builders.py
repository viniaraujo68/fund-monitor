from datetime import date, timedelta
from decimal import Decimal

import polars as pl

from fund_monitor.calc.benchmarks import benchmark_levels


def business_days(start: date, count: int) -> list[date]:
    days = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def quotas_frame(series_id: str, days: list[date], quotas: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "series_id": [series_id] * len(days),
            "cnpj": [series_id] * len(days),
            "subclass_id": [None] * len(days),
            "date": days,
            "quota_value": [Decimal(f"{quota:.12f}") for quota in quotas],
            "inherited": [False] * len(days),
        },
        schema_overrides={"quota_value": pl.Decimal(28, 12), "subclass_id": pl.String},
    )


def levels_frame(days: list[date], cdi_percent: float, ima_b: list[float] | None = None) -> pl.DataFrame:
    indices = pl.DataFrame(
        {"index": "cdi", "date": days, "value": [Decimal(str(cdi_percent))] * len(days), "unit": "percent_per_day"},
        schema_overrides={"value": pl.Decimal(18, 8)},
    )
    ima = pl.DataFrame(
        {"index": "IMA-B", "date": days if ima_b else [], "value": ima_b or []},
        schema={"index": pl.String, "date": pl.Date, "value": pl.Float64},
    )
    ibovespa = pl.DataFrame(schema={"index": pl.String, "date": pl.Date, "value": pl.Float64})
    return benchmark_levels(indices, ima, ibovespa)


def compound(start: float, returns: list[float]) -> list[float]:
    values = [start]
    for daily_return in returns:
        values.append(values[-1] * (1 + daily_return))
    return values
