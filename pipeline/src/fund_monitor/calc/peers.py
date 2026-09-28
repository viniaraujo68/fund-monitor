from datetime import date

import polars as pl

from fund_monitor.calc.returns import daily_returns, window_returns
from fund_monitor.calc.risk import risk_metrics
from fund_monitor.calc.series import deduplicate_reports, own_rows, quota_series, series_id

PEER_WINDOW = "12m"
MIN_PEER_NET_ASSETS = 50_000_000
MIN_PEERS = 5
PEER_METRICS = ("fund_return", "volatility", "max_drawdown")
GROUP_KEY = ["anbima_classification", "target_audience"]


def series_metrics(
    daily: pl.DataFrame, series: pl.DataFrame, levels: pl.DataFrame, as_of: date
) -> pl.DataFrame:
    quotas = quota_series(daily, series)
    windows = window_returns(quotas, levels, as_of).filter(pl.col("window") == PEER_WINDOW)
    risk = risk_metrics(quotas, daily_returns(quotas), levels, windows)
    latest_assets = (
        own_rows(daily, series)
        .filter(pl.col("date") <= as_of)
        .group_by("series_id")
        .agg(pl.col("net_assets").sort_by("date").last().cast(pl.Float64).alias("net_assets"))
    )
    return (
        windows.select("series_id", "fund_return")
        .join(risk.select("series_id", "volatility", "max_drawdown"), on="series_id", how="left")
        .join(latest_assets, on="series_id", how="left")
    )


def peer_table(peer_daily: pl.DataFrame, candidates: pl.DataFrame, levels: pl.DataFrame, as_of: date) -> pl.DataFrame:
    metrics = series_metrics(deduplicate_reports(peer_daily), candidates, levels, as_of)
    attributes = candidates.with_columns(series_id()).select("series_id", "cnpj", "class_name", *GROUP_KEY)
    eligible = (
        pl.all_horizontal(pl.col(metric).is_not_null() for metric in PEER_METRICS)
        & (pl.col("net_assets") > MIN_PEER_NET_ASSETS)
    )
    return attributes.join(metrics, on="series_id", how="left").with_columns(eligible.fill_null(False).alias("eligible"))


def percentile_rank(metric: str) -> pl.Expr:
    peer_value, own_value = pl.col(f"{metric}_peer"), pl.col(metric)
    below = (peer_value < own_value).sum() + 0.5 * (peer_value == own_value).sum()
    return (below / pl.len()).alias(f"{metric}_percentile")


def peer_positions(funds: pl.DataFrame, peers: pl.DataFrame) -> pl.DataFrame:
    members = peers.filter("eligible").select(
        "cnpj", *GROUP_KEY, *(pl.col(metric).alias(f"{metric}_peer") for metric in PEER_METRICS)
    )
    subjects = funds.filter(pl.all_horizontal(pl.col(metric).is_not_null() for metric in PEER_METRICS))
    pairs = subjects.join(members, on=GROUP_KEY, suffix="_peer").filter(pl.col("cnpj") != pl.col("cnpj_peer"))
    positions = pairs.group_by("series_id").agg(
        pl.len().alias("peer_count"),
        *(percentile_rank(metric) for metric in PEER_METRICS),
        *(
            pl.col(f"{metric}_peer").quantile(quantile, interpolation="linear").alias(f"{metric}_{label}")
            for metric in PEER_METRICS
            for label, quantile in (("p25", 0.25), ("median", 0.5), ("p75", 0.75))
        ),
    )
    enough = pl.col("peer_count") >= MIN_PEERS
    measured = [column for column in positions.columns if column not in ("series_id", "peer_count")]
    return (
        funds.select("series_id", *GROUP_KEY)
        .join(positions, on="series_id", how="left")
        .with_columns(pl.col("peer_count").fill_null(0))
        .with_columns(pl.when(enough).then(pl.col(column)).alias(column) for column in measured)
        .sort("series_id")
    )
