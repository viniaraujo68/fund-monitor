import logging
from datetime import date

import polars as pl

from fund_monitor import config
from fund_monitor.calc.returns import daily_returns
from fund_monitor.calc.series import complete_as_of, deduplicate_reports, load_daily, quota_series, series_id
from fund_monitor.quality.checks import QualityInputs, checked_days, market_jump_share, run_checks
from fund_monitor.universe import select_manager_series, select_monitored_series, select_peer_universe

logger = logging.getLogger(__name__)

QUALITY_ISSUES_PARQUET = "quality_issues"


def source_dates() -> dict[str, date | None]:
    indices = pl.read_parquet(config.INDICES_PARQUET)
    ima = pl.read_parquet(config.IMA_PARQUET)
    return {
        "cvm_daily": load_daily(config.DAILY_PARQUET_DIR)["date"].max(),
        "cdi": indices.filter(pl.col("index") == "cdi")["date"].max(),
        "ima_b": ima.filter(pl.col("index") == "IMA-B")["date"].max(),
        "ibov": pl.read_parquet(config.IBOVESPA_PARQUET)["date"].max(),
    }


def peer_market_jumps(registry: pl.DataFrame) -> pl.DataFrame:
    candidates = select_peer_universe(registry, config.MANAGER_CNPJ)
    quotas = quota_series(deduplicate_reports(load_daily(config.PEER_DAILY_PARQUET_DIR)), candidates)
    classification = candidates.with_columns(series_id()).select("series_id", "cvm_classification")
    return market_jump_share(daily_returns(quotas).join(classification, on="series_id"))


def build_inputs(registry: pl.DataFrame, reference_date: date) -> QualityInputs:
    raw_daily = load_daily(config.DAILY_PARQUET_DIR)
    monitored = select_monitored_series(registry, config.MANAGER_CNPJ)
    as_of = complete_as_of(quota_series(deduplicate_reports(raw_daily), monitored))
    raw_daily = raw_daily.filter(pl.col("date") <= as_of)
    daily = deduplicate_reports(raw_daily)
    quotas = quota_series(daily, monitored)
    indices = pl.read_parquet(config.INDICES_PARQUET)
    return QualityInputs(
        raw_daily=raw_daily,
        daily=daily,
        manager_series=select_manager_series(registry, config.MANAGER_CNPJ),
        monitored=monitored,
        quotas=quotas,
        returns=daily_returns(quotas),
        monthly_flows=pl.read_parquet(config.METRICS_DIR / "monthly_flows.parquet"),
        windows=pl.read_parquet(config.METRICS_DIR / "window_returns.parquet"),
        calendar=indices.filter(pl.col("index") == "cdi")["date"].sort().to_list(),
        market_jump_share=peer_market_jumps(registry),
        source_dates=source_dates(),
        as_of=as_of,
        reference_date=reference_date,
    )


def write_metric(name: str, frame: pl.DataFrame) -> None:
    config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(config.METRICS_DIR / f"{name}.parquet", compression="zstd")


def run_quality(registry: pl.DataFrame, reference_date: date) -> pl.DataFrame:
    inputs = build_inputs(registry, reference_date)
    issues = run_checks(inputs)
    coverage = pl.DataFrame({"checked_series": [inputs.quotas["series_id"].n_unique()], "checked_days": [checked_days(inputs)]})
    sources = pl.DataFrame({source: [last] for source, last in inputs.source_dates.items()}, schema={s: pl.Date for s in inputs.source_dates})
    write_metric(QUALITY_ISSUES_PARQUET, issues)
    write_metric("quality_checked_days", coverage)
    write_metric("quality_source_dates", sources)
    by_severity = dict(issues.group_by("severity").len().iter_rows())
    logger.info("quality: %d issues %s over %d series-days", issues.height, by_severity, coverage["checked_days"].item())
    return issues
