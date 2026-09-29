import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

import polars as pl

from fund_monitor import config
from fund_monitor.calc.engine import calculate, write_metrics
from fund_monitor.collect.anbima_ima import collect_ima
from fund_monitor.collect.b3_indices import collect_b3_indices
from fund_monitor.collect.bcb_sgs import collect_bcb
from fund_monitor.collect.cvm_daily import DailyTarget, collect_daily, reported_subclasses
from fund_monitor.collect.cvm_registry import collect_registry, write_registry
from fund_monitor.publish.site_json import publish_site
from fund_monitor.quality.report import run_quality
from fund_monitor.universe import (
    GENERAL_PUBLIC,
    mark_reported_subclasses,
    select_manager_series,
    select_monitored_series,
    select_peer_universe,
)

STAGES = ("collect", "calc", "quality", "publish")
REFERENCE_DATE = datetime.now(ZoneInfo("America/Sao_Paulo")).date()

logger = logging.getLogger("fund_monitor")


def run_collect(reference_date: date) -> None:
    run_collect_cvm(reference_date)
    collect_bcb(config.WINDOW_START, reference_date)
    collect_ima(config.WINDOW_START, reference_date)
    collect_b3_indices(config.WINDOW_START, reference_date)


def run_collect_cvm(reference_date: date) -> None:
    registry = collect_registry(reference_date)
    candidates = mark_reported_subclasses(registry, registry["subclass_id"].drop_nulls())
    manager_series = select_manager_series(candidates, config.MANAGER_CNPJ)
    peers = select_peer_universe(candidates, config.MANAGER_CNPJ)
    targets = [
        DailyTarget("manager", frozenset(manager_series["cnpj"]), config.DAILY_PARQUET_DIR),
        DailyTarget("peers", frozenset(peers["cnpj"]), config.PEER_DAILY_PARQUET_DIR, config.PEER_DAILY_COLUMNS),
    ]
    months = collect_daily(config.WINDOW_START, reference_date, targets)
    logger.info("daily reports collected for %d months", len(months))
    reported = reported_subclasses([config.DAILY_PARQUET_DIR, config.PEER_DAILY_PARQUET_DIR])
    registry = mark_reported_subclasses(registry, reported)
    write_registry(registry)
    log_universe(registry)


def log_universe(registry: pl.DataFrame) -> None:
    manager_series = select_manager_series(registry, config.MANAGER_CNPJ)
    monitored = select_monitored_series(registry, config.MANAGER_CNPJ)
    logger.info(
        "universe: %d active series of the manager, %d monitored (non-exclusive), %d general public",
        manager_series.height,
        monitored.height,
        monitored.filter(pl.col("target_audience") == GENERAL_PUBLIC).height,
    )
    peers = select_peer_universe(registry, config.MANAGER_CNPJ)
    logger.info("peers: %d candidate series in %d classes", peers.height, peers["cnpj"].n_unique())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if "collect" in STAGES:
        run_collect(REFERENCE_DATE)
    if "calc" in STAGES:
        write_metrics(calculate(pl.read_parquet(config.REGISTRY_PARQUET)))
    if "quality" in STAGES:
        run_quality(pl.read_parquet(config.REGISTRY_PARQUET), REFERENCE_DATE)
    if "publish" in STAGES:
        publish_site(pl.read_parquet(config.REGISTRY_PARQUET), REFERENCE_DATE)


if __name__ == "__main__":
    main()
