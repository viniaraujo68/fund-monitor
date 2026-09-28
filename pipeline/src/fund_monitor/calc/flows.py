from datetime import date

import polars as pl

from fund_monitor.calc.returns import subtract_months
from fund_monitor.validation import ensure_unique

MONEY_COLUMNS = ("net_assets", "inflows", "outflows")


def as_float(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(pl.col(c).cast(pl.Float64) for c in MONEY_COLUMNS).with_columns(
        net_flow=pl.col("inflows") - pl.col("outflows")
    )


def monthly_flows(rows: pl.DataFrame, quotas: pl.DataFrame) -> pl.DataFrame:
    month = pl.col("date").dt.truncate("1mo").alias("month")
    flows = (
        as_float(rows)
        .group_by("series_id", month)
        .agg(
            pl.col("net_flow").sum(),
            pl.col("inflows").sum(),
            pl.col("outflows").sum(),
            pl.col("net_assets").sort_by("date").last().alias("net_assets_end"),
            pl.col("shareholders").sort_by("date").last().alias("shareholders_end"),
            pl.col("date").max().alias("last_report_date"),
        )
    )
    month_end_quota = quotas.group_by("series_id", month).agg(
        pl.col("quota_value").sort_by("date").last().cast(pl.Float64).alias("quota_end")
    )
    return (
        flows.join(month_end_quota, on=["series_id", "month"], how="left")
        .sort("series_id", "month")
        .with_columns(
            pl.col("net_assets_end").shift(1).over("series_id").alias("net_assets_start"),
            (pl.col("quota_end") / pl.col("quota_end").shift(1).over("series_id") - 1).alias("monthly_return"),
        )
        .with_columns(
            (
                pl.col("net_assets_end")
                - pl.col("net_assets_start")
                - pl.col("net_flow")
                - pl.col("net_assets_start") * pl.col("monthly_return")
            ).alias("unexplained_change")
        )
        .with_columns((pl.col("unexplained_change") / pl.col("net_assets_start")).alias("unexplained_share"))
        .drop("quota_end")
    )


def flow_summary(rows: pl.DataFrame, as_of: date) -> pl.DataFrame:
    year_ago = subtract_months(as_of, 12)
    daily = as_float(rows).filter(pl.col("date") <= as_of).sort("series_id", "date")
    latest = daily.group_by("series_id").agg(
        pl.col("date").min().alias("first_report_date"),
        pl.col("date").max().alias("last_report_date"),
        pl.col("net_assets").sort_by("date").last().alias("net_assets"),
        pl.col("shareholders").sort_by("date").last().alias("shareholders"),
        pl.col("net_flow").filter(pl.col("date") > year_ago).sum().alias("net_flow_12m"),
    )
    year_ago_values = (
        daily.filter(pl.col("date") <= year_ago)
        .group_by("series_id")
        .agg(
            pl.col("net_assets").sort_by("date").last().alias("net_assets_12m_ago"),
            pl.col("shareholders").sort_by("date").last().alias("shareholders_12m_ago"),
        )
    )
    return (
        latest.join(year_ago_values, on="series_id", how="left")
        .with_columns(
            (pl.col("first_report_date") > year_ago).alias("flow_window_partial"),
            (pl.col("shareholders") - pl.col("shareholders_12m_ago")).alias("shareholders_change_12m"),
            (pl.col("net_assets") / pl.col("net_assets_12m_ago") - 1).alias("net_assets_change_12m"),
        )
        .sort("series_id")
    )


def class_snapshots(frame: pl.DataFrame, *period: str) -> pl.DataFrame:
    series = frame.group_by("cnpj", "subclass_id", *period).agg(
        pl.col("net_flow").sum(), pl.col("net_assets").sort_by("date").last()
    )
    superseded = pl.col("subclass_id").is_null() & pl.col("subclass_id").is_not_null().any().over("cnpj", *period)
    return (
        series.with_columns(superseded.alias("superseded"))
        .group_by("cnpj", *period)
        .agg(pl.col("net_flow").sum(), pl.col("net_assets").filter(pl.col("superseded").not_()).sum())
    )


def aggregate_monthly(rows: pl.DataFrame, attributes: pl.DataFrame, group_column: str) -> pl.DataFrame:
    monthly = as_float(rows).with_columns(pl.col("date").dt.truncate("1mo").alias("month"))
    labels = attributes.select("cnpj", group_column).unique()
    ensure_unique(labels, ["cnpj"], f"class-level labels for {group_column}")
    return (
        class_snapshots(monthly, "month")
        .join(labels, on="cnpj", how="left")
        .group_by(group_column, "month")
        .agg(pl.col("net_flow").sum(), pl.col("net_assets").sum().alias("net_assets_end"), pl.len().alias("classes"))
        .sort(group_column, "month")
    )


def aggregate_totals(rows: pl.DataFrame, as_of: date) -> dict[str, float]:
    year_ago = subtract_months(as_of, 12)
    daily = as_float(rows).filter(pl.col("date") <= as_of)
    latest = class_snapshots(daily)
    return {
        "net_assets": latest["net_assets"].sum(),
        "net_flow_12m": daily.filter(pl.col("date") > year_ago)["net_flow"].sum(),
        "classes": latest.height,
    }
