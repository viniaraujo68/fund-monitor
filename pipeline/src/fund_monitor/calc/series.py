from datetime import date, timedelta
from pathlib import Path

import polars as pl

SERIES_KEY = ["cnpj", "subclass_id"]
PREFERRED_REPORT_TYPE = "CLASSES - FIF"
MAX_HANDOFF_GAP = timedelta(days=7)
COMPLETE_DAY_SHARE = 0.9
COVERAGE_LOOKBACK_DAYS = 20
QUOTA_COLUMNS = ["series_id", "cnpj", "subclass_id", "date", "quota_value", "inherited"]


def series_id() -> pl.Expr:
    return (
        pl.when(pl.col("subclass_id").is_null())
        .then(pl.col("cnpj"))
        .otherwise(pl.concat_str("cnpj", pl.lit("-"), "subclass_id"))
        .alias("series_id")
    )


def load_daily(directory: Path) -> pl.DataFrame:
    return pl.read_parquet(directory / "*.parquet")


def deduplicate_reports(daily: pl.DataFrame) -> pl.DataFrame:
    return (
        daily.with_columns((pl.col("report_type") != PREFERRED_REPORT_TYPE).alias("is_fallback_report"))
        .sort(*SERIES_KEY, "date", "is_fallback_report", nulls_last=False)
        .unique(subset=[*SERIES_KEY, "date"], keep="first", maintain_order=True)
        .drop("is_fallback_report")
    )


def series_keys(series: pl.DataFrame) -> pl.DataFrame:
    return series.select(SERIES_KEY).unique().with_columns(series_id())


def own_rows(daily: pl.DataFrame, series: pl.DataFrame) -> pl.DataFrame:
    return daily.join(series_keys(series), on=SERIES_KEY, nulls_equal=True).sort("series_id", "date")


def valid_reports(daily: pl.DataFrame) -> pl.DataFrame:
    return daily.filter(pl.col("quota_value") > 0)


def quota_series(daily: pl.DataFrame, series: pl.DataFrame) -> pl.DataFrame:
    valid = valid_reports(daily)
    own = own_rows(valid, series).with_columns(inherited=pl.lit(False))
    first_own = own.group_by("series_id").agg(pl.col("date").min().alias("first_own_date"))
    heirs = series_keys(series).filter(pl.col("subclass_id").is_not_null()).join(first_own, on="series_id")
    class_rows = (
        valid.filter(pl.col("subclass_id").is_null())
        .drop("subclass_id")
        .join(heirs, on="cnpj")
        .filter(pl.col("date") < pl.col("first_own_date"))
    )
    continuous = (
        class_rows.group_by("series_id")
        .agg(pl.col("date").max().alias("last_class_date"), pl.col("first_own_date").first())
        .filter(pl.col("first_own_date") - pl.col("last_class_date") <= MAX_HANDOFF_GAP)
        .select("series_id")
    )
    inherited = class_rows.join(continuous, on="series_id").with_columns(inherited=pl.lit(True))
    return pl.concat([own.select(QUOTA_COLUMNS), inherited.select(QUOTA_COLUMNS)]).sort("series_id", "date")


def split_dates(daily: pl.DataFrame) -> pl.DataFrame:
    return (
        daily.filter(pl.col("subclass_id").is_not_null())
        .group_by("cnpj")
        .agg(pl.col("date").min().alias("split_date"))
    )


def subclassed_cnpjs(series: pl.DataFrame) -> pl.DataFrame:
    return series.filter(pl.col("subclass_id").is_not_null()).select("cnpj").unique()


def aggregate_rows(daily: pl.DataFrame, series: pl.DataFrame) -> pl.DataFrame:
    before_split = (
        daily.filter(pl.col("subclass_id").is_null())
        .join(subclassed_cnpjs(series), on="cnpj")
        .join(split_dates(daily), on="cnpj", how="left")
        .filter(pl.col("split_date").is_null() | (pl.col("date") < pl.col("split_date")))
        .drop("split_date")
    )
    own = daily.join(series.select(SERIES_KEY).unique(), on=SERIES_KEY, nulls_equal=True)
    return pl.concat([own, before_split.select(own.columns)]).unique().sort("cnpj", "date")


def complete_as_of(quotas: pl.DataFrame) -> date:
    coverage = quotas.group_by("date").agg(pl.col("series_id").n_unique().alias("series")).sort("date")
    recent = coverage.tail(COVERAGE_LOOKBACK_DAYS)
    threshold = COMPLETE_DAY_SHARE * recent["series"].max()
    return recent.filter(pl.col("series") >= threshold)["date"].max()
