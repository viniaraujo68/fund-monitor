import logging
from datetime import date

import polars as pl

from fund_monitor import config
from fund_monitor.calc.benchmarks import benchmark_levels
from fund_monitor.calc.flows import aggregate_monthly, flow_summary, monthly_flows
from fund_monitor.calc.peers import GROUP_KEY, PEER_WINDOW, peer_positions, peer_table
from fund_monitor.calc.returns import cumulative_index, daily_returns, rolling_12m_returns, subtract_months, window_returns
from fund_monitor.calc.risk import drawdown_series, risk_metrics
from fund_monitor.calc.series import (
    aggregate_rows,
    complete_as_of,
    deduplicate_reports,
    load_daily,
    own_rows,
    quota_series,
    series_id,
)
from fund_monitor.universe import select_manager_series, select_monitored_series, select_peer_universe

logger = logging.getLogger(__name__)

CHART_MONTHS = 24
AGGREGATE_GROUPS = ("cvm_classification", "anbima_classification")
AGGREGATE_SCOPES = {"monitored": select_monitored_series, "manager": select_manager_series}


def aggregates(daily: pl.DataFrame, registry: pl.DataFrame) -> pl.DataFrame:
    frames = []
    for scope, select in AGGREGATE_SCOPES.items():
        series = select(registry, config.MANAGER_CNPJ)
        rows = aggregate_rows(daily, series)
        attributes = series.select("cnpj", *AGGREGATE_GROUPS).unique()
        for group in AGGREGATE_GROUPS:
            frames.append(
                aggregate_monthly(rows, attributes, group)
                .rename({group: "group_value"})
                .with_columns(scope=pl.lit(scope), group=pl.lit(group))
            )
    return pl.concat(frames).select("scope", "group", "group_value", "month", "net_flow", "net_assets_end", "classes")


def peer_subjects(monitored: pl.DataFrame, windows: pl.DataFrame, risk: pl.DataFrame) -> pl.DataFrame:
    attributes = monitored.with_columns(series_id()).select("series_id", "cnpj", *GROUP_KEY)
    returns = windows.filter(pl.col("window") == PEER_WINDOW).select("series_id", "fund_return")
    risks = risk.filter(pl.col("window") == PEER_WINDOW).select("series_id", "volatility", "max_drawdown")
    return attributes.join(returns, on="series_id", how="left").join(risks, on="series_id", how="left")


def calculate(registry: pl.DataFrame) -> dict[str, pl.DataFrame]:
    daily = deduplicate_reports(load_daily(config.DAILY_PARQUET_DIR))
    levels = benchmark_levels(
        pl.read_parquet(config.INDICES_PARQUET), pl.read_parquet(config.IMA_PARQUET), pl.read_parquet(config.IBOVESPA_PARQUET)
    )
    monitored = select_monitored_series(registry, config.MANAGER_CNPJ)
    as_of = complete_as_of(quota_series(daily, monitored))
    daily = daily.filter(pl.col("date") <= as_of)
    quotas = quota_series(daily, monitored)
    returns = daily_returns(quotas)
    windows = window_returns(quotas, levels, as_of)
    cumulative = cumulative_index(quotas, levels, subtract_months(as_of, CHART_MONTHS))
    flow_rows = own_rows(daily, monitored)
    risk = risk_metrics(quotas, returns, levels, windows)
    peer_daily = load_daily(config.PEER_DAILY_PARQUET_DIR).filter(pl.col("date") <= as_of)
    peers = peer_table(peer_daily, select_peer_universe(registry, config.MANAGER_CNPJ), levels, as_of)
    metrics = {
        "window_returns": windows,
        "risk": risk,
        "peers": peers,
        "peer_positions": peer_positions(peer_subjects(monitored, windows, risk), peers),
        "rolling_12m": rolling_12m_returns(quotas, levels),
        "cumulative_index": cumulative,
        "drawdown": drawdown_series(cumulative),
        "monthly_flows": monthly_flows(flow_rows, quotas),
        "flow_summary": flow_summary(flow_rows, as_of),
        "aggregate_monthly": aggregates(daily, registry),
    }
    logger.info("calc: as of %s, %d series, %d quota rows", as_of, quotas["series_id"].n_unique(), quotas.height)
    return metrics


def write_metrics(metrics: dict[str, pl.DataFrame]) -> None:
    config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
    for name, frame in metrics.items():
        frame.write_parquet(config.METRICS_DIR / f"{name}.parquet", compression="zstd")
        logger.info("metrics %s: %d rows", name, frame.height)
