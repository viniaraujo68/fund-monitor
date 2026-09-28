import math

import polars as pl

from fund_monitor.calc.benchmarks import IBOVESPA, IMA_B, attach_level
from fund_monitor.calc.returns import TRADING_DAYS_PER_YEAR, daily_returns

RISK_WINDOWS = ("12m", "24m")
MIN_OBSERVATIONS = 60
ANNUALIZATION = math.sqrt(TRADING_DAYS_PER_YEAR)
MARKET_BENCHMARKS = (IMA_B, IBOVESPA)


def with_benchmark_returns(returns: pl.DataFrame, levels: pl.DataFrame) -> pl.DataFrame:
    frame = returns
    for benchmark in MARKET_BENCHMARKS:
        frame = attach_level(frame, levels, benchmark, "date", f"{benchmark}_level")
    return frame.sort("series_id", "date").with_columns(
        (pl.col(f"{b}_level") / pl.col(f"{b}_level").shift(1).over("series_id") - 1).alias(f"{b}_daily_return")
        for b in MARKET_BENCHMARKS
    )


def rows_in_windows(frame: pl.DataFrame, windows: pl.DataFrame, include_base: bool) -> pl.DataFrame:
    selected = windows.filter(pl.col("window").is_in(RISK_WINDOWS), pl.col("fund_return").is_not_null())
    after_base = pl.col("date") >= pl.col("base_date") if include_base else pl.col("date") > pl.col("base_date")
    return (
        frame.join(selected.select("series_id", "window", "base_date", "end_date"), on="series_id")
        .filter(after_base, pl.col("date") <= pl.col("end_date"))
        .sort("series_id", "window", "date")
    )


def paired_returns(benchmark: str) -> tuple[pl.Expr, pl.Expr]:
    fund, market = pl.col("daily_return"), pl.col(f"{benchmark}_daily_return")
    both = fund.is_not_null() & market.is_not_null()
    return fund.filter(both), market.filter(both)


def beta(benchmark: str) -> pl.Expr:
    fund, market = paired_returns(benchmark)
    return (pl.cov(fund, market) / market.var()).alias(f"beta_{benchmark}")


def tracking_error(benchmark: str) -> pl.Expr:
    fund, market = paired_returns(benchmark)
    return ((fund - market).std() * ANNUALIZATION).alias(f"tracking_error_{benchmark}")


def return_statistics(returns: pl.DataFrame, levels: pl.DataFrame, windows: pl.DataFrame) -> pl.DataFrame:
    rows = rows_in_windows(with_benchmark_returns(returns, levels), windows, include_base=False)
    enough = pl.col("observations") >= MIN_OBSERVATIONS
    statistics = rows.group_by("series_id", "window").agg(
        pl.col("daily_return").count().alias("observations"),
        (pl.col("daily_return").std() * ANNUALIZATION).alias("volatility"),
        (pl.col("daily_return") > 0).mean().alias("positive_days_share"),
        pl.col("daily_return").min().alias("worst_day"),
        pl.col("date").sort_by("daily_return").first().alias("worst_day_date"),
        pl.col("daily_return").max().alias("best_day"),
        pl.col("date").sort_by("daily_return").last().alias("best_day_date"),
        *(beta(benchmark) for benchmark in MARKET_BENCHMARKS),
        *(tracking_error(benchmark) for benchmark in MARKET_BENCHMARKS),
    )
    measured = [c for c in statistics.columns if c not in ("series_id", "window", "observations")]
    return statistics.with_columns(pl.when(enough).then(pl.col(c)).alias(c) for c in measured)


def max_drawdown(quotas: pl.DataFrame, windows: pl.DataFrame) -> pl.DataFrame:
    rows = rows_in_windows(
        quotas.with_columns(quota=pl.col("quota_value").cast(pl.Float64)), windows, include_base=True
    ).with_columns(running_peak=pl.col("quota").cum_max().over("series_id", "window"))
    rows = rows.with_columns(drawdown=pl.col("quota") / pl.col("running_peak") - 1)
    troughs = rows.group_by("series_id", "window").agg(
        pl.col("drawdown").min().alias("max_drawdown"),
        pl.col("date").sort_by("drawdown").first().alias("trough_date"),
        pl.col("running_peak").sort_by("drawdown").first().alias("peak_quota"),
    )
    located = rows.join(troughs, on=["series_id", "window"])
    peaks = (
        located.filter(pl.col("date") <= pl.col("trough_date"), pl.col("quota") == pl.col("peak_quota"))
        .group_by("series_id", "window")
        .agg(pl.col("date").max().alias("peak_date"))
    )
    recoveries = (
        located.filter(pl.col("date") > pl.col("trough_date"), pl.col("quota") >= pl.col("peak_quota"))
        .group_by("series_id", "window")
        .agg(pl.col("date").min().alias("recovery_date"))
    )
    return (
        troughs.join(peaks, on=["series_id", "window"], how="left")
        .join(recoveries, on=["series_id", "window"], how="left")
        .with_columns(
            pl.when(pl.col("max_drawdown") < 0).then(pl.col(c)).alias(c)
            for c in ("trough_date", "peak_date", "recovery_date")
        )
        .select("series_id", "window", "max_drawdown", "peak_date", "trough_date", "recovery_date")
    )


def drawdown_series(cumulative: pl.DataFrame) -> pl.DataFrame:
    return cumulative.sort("series_id", "date").select(
        "series_id",
        "date",
        (pl.col("fund_index") / pl.col("fund_index").cum_max().over("series_id") - 1).alias("drawdown"),
    )


def risk_metrics(quotas: pl.DataFrame, levels: pl.DataFrame, windows: pl.DataFrame) -> pl.DataFrame:
    statistics = return_statistics(daily_returns(quotas), levels, windows)
    drawdowns = max_drawdown(quotas, windows)
    sharpe_inputs = windows.select("series_id", "window", "fund_annualized", "cdi_annualized")
    return (
        statistics.join(drawdowns, on=["series_id", "window"], how="left")
        .join(sharpe_inputs, on=["series_id", "window"], how="left")
        .with_columns(
            ((pl.col("fund_annualized") - pl.col("cdi_annualized")) / pl.col("volatility")).alias("sharpe")
        )
        .drop("fund_annualized", "cdi_annualized")
        .sort("series_id", "window")
    )
