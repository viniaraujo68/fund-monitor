import calendar
from datetime import date, timedelta

import polars as pl

from fund_monitor.calc.benchmarks import CDI, MARKET_BENCHMARKS, attach_accruals, attach_level

TRADING_DAYS_PER_YEAR = 252
MONTHLY_WINDOWS = {"3m": 3, "6m": 6, "12m": 12, "24m": 24}
SINCE_START = "since_start"
MIN_MONTHS_TO_ANNUALIZE = 12
MAX_QUOTA_STALENESS = timedelta(days=7)
BENCHMARKS = (CDI, *MARKET_BENCHMARKS)


def subtract_months(day: date, months: int) -> date:
    total = day.year * 12 + day.month - 1 - months
    year, month = divmod(total, 12)
    last_day = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(day.day, last_day))


def window_anchors(as_of: date) -> pl.DataFrame:
    previous_month_end = date(as_of.year, as_of.month, 1) - timedelta(days=1)
    rows = [
        ("mtd", previous_month_end, None),
        ("ytd", date(as_of.year - 1, 12, 31), None),
        *((name, subtract_months(as_of, months), months) for name, months in MONTHLY_WINDOWS.items()),
    ]
    return pl.DataFrame(rows, schema={"window": pl.String, "anchor_date": pl.Date, "months": pl.Int64}, orient="row")


def daily_returns(quotas: pl.DataFrame) -> pl.DataFrame:
    return (
        quotas.sort("series_id", "date")
        .with_columns(quota=pl.col("quota_value").cast(pl.Float64))
        .with_columns(daily_return=pl.col("quota") / pl.col("quota").shift(1).over("series_id") - 1)
    )


def attach_quota(frame: pl.DataFrame, quotas: pl.DataFrame, anchor_column: str, prefix: str) -> pl.DataFrame:
    right = quotas.select(
        "series_id",
        pl.col("date").alias(f"{prefix}_date"),
        pl.col("quota_value").cast(pl.Float64).alias(f"{prefix}_quota"),
    ).sort(f"{prefix}_date")
    return frame.sort(anchor_column).join_asof(
        right, left_on=anchor_column, right_on=f"{prefix}_date", by="series_id", strategy="backward",
        check_sortedness=False,
    )


def attach_period_benchmarks(frame: pl.DataFrame, levels: pl.DataFrame) -> pl.DataFrame:
    for benchmark in BENCHMARKS:
        frame = attach_level(frame, levels, benchmark, "base_date", f"{benchmark}_base")
        frame = attach_level(frame, levels, benchmark, "end_date", f"{benchmark}_end")
    frame = attach_accruals(frame, levels, "base_date", "base_accruals")
    frame = attach_accruals(frame, levels, "end_date", "end_accruals")
    return frame.with_columns(
        *((pl.col(f"{benchmark}_end") / pl.col(f"{benchmark}_base") - 1).alias(f"{benchmark}_return") for benchmark in BENCHMARKS),
        (pl.col("end_accruals") - pl.col("base_accruals")).alias("business_days"),
    ).drop(
        *(f"{benchmark}_{side}" for benchmark in BENCHMARKS for side in ("base", "end")),
        "base_accruals",
        "end_accruals",
    )


def annualize(total_return: pl.Expr) -> pl.Expr:
    return (1 + total_return) ** (TRADING_DAYS_PER_YEAR / pl.col("business_days")) - 1


def window_returns(quotas: pl.DataFrame, levels: pl.DataFrame, as_of: date) -> pl.DataFrame:
    spans = quotas.group_by("series_id").agg(
        pl.col("date").min().alias("first_date"),
        pl.col("date").max().alias("last_date"),
        pl.col("date").filter(pl.col("inherited")).max().alias("inherited_until"),
    )
    fixed = spans.join(window_anchors(as_of), how="cross")
    since_start = spans.with_columns(
        window=pl.lit(SINCE_START), anchor_date=pl.col("first_date"), months=pl.lit(None, dtype=pl.Int64)
    ).select(fixed.columns)
    grid = pl.concat([fixed, since_start]).with_columns(
        as_of=pl.lit(as_of), has_history=pl.col("first_date") <= pl.col("anchor_date")
    )
    grid = attach_quota(grid, quotas, "anchor_date", "base")
    grid = attach_quota(grid, quotas, "as_of", "end")
    grid = attach_period_benchmarks(grid, levels).with_columns(
        stale=pl.col("end_date") < pl.lit(as_of - MAX_QUOTA_STALENESS)
    )
    long_enough = (pl.col("months") >= MIN_MONTHS_TO_ANNUALIZE) | (
        (pl.col("window") == SINCE_START) & (pl.col("business_days") >= TRADING_DAYS_PER_YEAR)
    )
    return (
        grid.with_columns(
            pl.when(pl.col("has_history")).then(pl.col("end_quota") / pl.col("base_quota") - 1).alias("fund_return"),
            (long_enough & pl.col("stale").not_()).alias("annualizable"),
        )
        .with_columns(
            pl.when("annualizable").then(annualize(pl.col("fund_return"))).alias("fund_annualized"),
            pl.when("annualizable").then(annualize(pl.col("cdi_return"))).alias("cdi_annualized"),
            pl.when(pl.col("stale").not_() & (pl.col("cdi_return") > 0))
            .then(pl.col("fund_return") / pl.col("cdi_return"))
            .alias("pct_cdi"),
            *((pl.col("fund_return") - pl.col(f"{b}_return")).alias(f"excess_{b}") for b in BENCHMARKS),
        )
        .drop("base_quota", "end_quota", "as_of")
        .sort("series_id", "window")
    )


def cumulative_index(quotas: pl.DataFrame, levels: pl.DataFrame, start: date) -> pl.DataFrame:
    anchors = quotas.group_by("series_id").agg(pl.col("date").min().alias("first_date")).with_columns(
        anchor_date=pl.max_horizontal(pl.col("first_date"), pl.lit(start))
    )
    bases = attach_quota(anchors, quotas, "anchor_date", "base")
    rows = (
        quotas.join(bases.select("series_id", "base_date", "base_quota"), on="series_id")
        .filter(pl.col("date") >= pl.col("base_date"))
        .with_columns(quota=pl.col("quota_value").cast(pl.Float64))
    )
    for benchmark in BENCHMARKS:
        rows = attach_level(rows, levels, benchmark, "date", f"{benchmark}_level")
        rows = attach_level(rows, levels, benchmark, "base_date", f"{benchmark}_base")
    return rows.select(
        "series_id",
        "date",
        "inherited",
        (100 * pl.col("quota") / pl.col("base_quota")).alias("fund_index"),
        *((100 * pl.col(f"{b}_level") / pl.col(f"{b}_base")).alias(f"{b}_index") for b in BENCHMARKS),
    ).sort("series_id", "date")
