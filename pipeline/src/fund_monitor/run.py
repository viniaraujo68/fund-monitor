import logging
from datetime import date

import polars as pl

from fund_monitor import config
from fund_monitor.collect.cvm_daily import collect_daily
from fund_monitor.collect.cvm_registry import collect_registry
from fund_monitor.universe import GENERAL_PUBLIC, select_manager_series, select_monitored_series

STAGES = ("collect",)
REFERENCE_DATE = date.today()

logger = logging.getLogger("fund_monitor")


def run_collect(reference_date: date) -> None:
    registry = collect_registry(reference_date)
    manager_series = select_manager_series(registry, config.MANAGER_CNPJ)
    monitored = select_monitored_series(registry, config.MANAGER_CNPJ)
    logger.info(
        "universe: %d active series of the manager, %d monitored (non-exclusive), %d general public",
        manager_series.height,
        monitored.height,
        monitored.filter(pl.col("target_audience") == GENERAL_PUBLIC).height,
    )
    cnpjs = set(manager_series["cnpj"].unique())
    months = collect_daily(config.WINDOW_START, reference_date, cnpjs)
    logger.info("daily reports collected for %d months", len(months))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if "collect" in STAGES:
        run_collect(REFERENCE_DATE)


if __name__ == "__main__":
    main()
