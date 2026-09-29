from collections.abc import Iterator
from datetime import date

import polars as pl
import pytest

from builders import MANAGER, SAMPLE_DAYS, SAMPLE_PEER_RATES, SAMPLE_ZEROED_DAY, install_sources, sample_sources
from fund_monitor import config
from fund_monitor.calc.engine import aggregates, calculate

DAYS = SAMPLE_DAYS
ZEROED_DAY = SAMPLE_ZEROED_DAY
PEER_RATES = SAMPLE_PEER_RATES


@pytest.fixture(scope="module")
def metrics(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, pl.DataFrame]]:
    daily, peer_daily, registry = sample_sources()
    with pytest.MonkeyPatch.context() as monkeypatch:
        install_sources(tmp_path_factory.mktemp("engine"), monkeypatch, daily, peer_daily, DAYS)
        yield calculate(registry)


def test_zeroed_report_leaves_flows_and_aggregates(metrics: dict[str, pl.DataFrame]) -> None:
    january = metrics["monthly_flows"].filter(pl.col("series_id") == "A", pl.col("month") == date(2026, 1, 1)).row(0, named=True)
    assert january["net_assets_end"] == pytest.approx(200_000_000)
    assert january["shareholders_end"] == 10
    assert january["last_report_date"] == date(2026, 1, 29)
    aggregate = metrics["aggregate_monthly"].filter(
        pl.col("scope") == "monitored", pl.col("structural"), pl.col("group") == "cvm_classification", pl.col("month") == date(2026, 1, 1)
    )
    assert aggregate["net_assets_end"].item() == pytest.approx(300_000_000)
    assert ZEROED_DAY not in metrics["cumulative_index"].filter(pl.col("series_id") == "A")["date"].to_list()


def test_engine_totals_cover_both_scopes(metrics: dict[str, pl.DataFrame]) -> None:
    totals = {row["scope"]: row for row in metrics["aggregate_totals"].filter(pl.col("structural")).iter_rows(named=True)}
    assert set(totals) == {"monitored", "manager"}
    assert totals["monitored"]["net_assets"] == pytest.approx(300_000_000)
    assert totals["monitored"]["classes"] == 2
    assert totals["monitored"]["as_of"] == DAYS[-1]


def test_engine_ranks_monitored_funds_against_other_classes(metrics: dict[str, pl.DataFrame]) -> None:
    position = metrics["peer_positions"].filter(pl.col("series_id") == "A").row(0, named=True)
    twelve_months = metrics["window_returns"].filter(pl.col("series_id") == "A", pl.col("window") == "12m").row(0, named=True)
    assert position["peer_count"] == 6
    assert position["fund_return"] == pytest.approx(twelve_months["fund_return"])
    assert position["fund_return_percentile"] == pytest.approx(3 / 6)
    assert metrics["peers"].filter(pl.col("cnpj").is_in(["A", "B", *PEER_RATES]))["eligible"].all()


def test_aggregates_without_structural_vehicles_leave_them_out(monkeypatch: pytest.MonkeyPatch) -> None:
    daily, _, registry = sample_sources()
    monkeypatch.setattr(config, "MANAGER_CNPJ", MANAGER)
    structural = registry.with_columns(
        pl.when(pl.col("cnpj") == "B").then(pl.lit("ICATU VANGUARDA BETA FIFE FIF - CLASSE")).otherwise(pl.col("class_name")).alias("class_name")
    )
    _, totals = aggregates(daily, structural, DAYS[-1])
    by_scope = {(row["scope"], row["structural"]): row for row in totals.iter_rows(named=True)}
    assert by_scope[("monitored", True)]["classes"] == 2
    assert by_scope[("monitored", False)]["classes"] == 1
    assert by_scope[("monitored", False)]["net_assets"] == pytest.approx(200_000_000)
    assert by_scope[("manager", False)]["classes"] == 1
