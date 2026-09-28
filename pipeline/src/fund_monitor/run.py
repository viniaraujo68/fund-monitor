import logging
from datetime import date

import polars as pl

from fund_monitor import config
from fund_monitor.calc.engine import calculate, write_metrics
from fund_monitor.collect.anbima_ima import collect_ima
from fund_monitor.collect.b3_ibovespa import collect_ibovespa
from fund_monitor.collect.bcb_sgs import collect_bcb
from fund_monitor.collect.cvm_daily import DailyTarget, collect_daily
from fund_monitor.collect.cvm_registry import collect_registry
from fund_monitor.universe import (
    GENERAL_PUBLIC,
    select_manager_series,
    select_monitored_series,
    select_peer_universe,
)

STAGES = ("collect", "calc")
REFERENCE_DATE = date.today()

logger = logging.getLogger("fund_monitor")


def run_collect(reference_date: date) -> None:
    run_collect_cvm(reference_date)
    collect_bcb(config.WINDOW_START, reference_date)
    collect_ima(config.WINDOW_START, reference_date)
    collect_ibovespa(config.WINDOW_START, reference_date)


def run_collect_cvm(reference_date: date) -> None:
    registry = collect_registry(reference_date)
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
    targets = [
        DailyTarget("manager", frozenset(manager_series["cnpj"]), config.DAILY_PARQUET_DIR),
        DailyTarget("peers", frozenset(peers["cnpj"]), config.PEER_DAILY_PARQUET_DIR, config.PEER_DAILY_COLUMNS),
    ]
    months = collect_daily(config.WINDOW_START, reference_date, targets)
    logger.info("daily reports collected for %d months", len(months))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if "collect" in STAGES:
        run_collect(REFERENCE_DATE)
    if "calc" in STAGES:
        write_metrics(calculate(pl.read_parquet(config.REGISTRY_PARQUET)))


if __name__ == "__main__":
    main()
