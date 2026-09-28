from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from builders import business_days, compound, levels_frame
from fund_monitor.calc.peers import MIN_PEER_NET_ASSETS, peer_positions, peer_table

GROUP = {"anbima_classification": "Renda Fixa Simples", "target_audience": "Público Geral"}


def peer(cnpj: str, fund_return: float, volatility: float, max_drawdown: float, eligible: bool = True) -> dict:
    return {"cnpj": cnpj, **GROUP, "fund_return": fund_return, "volatility": volatility, "max_drawdown": max_drawdown, "eligible": eligible}


def fund(series_id: str, cnpj: str, fund_return: float | None = 0.14) -> pl.DataFrame:
    return pl.DataFrame([{"series_id": series_id, "cnpj": cnpj, **GROUP, "fund_return": fund_return, "volatility": 0.01, "max_drawdown": -0.01}])


PEERS = pl.DataFrame(
    [
        peer("P1", 0.10, 0.005, -0.030),
        peer("P2", 0.12, 0.010, -0.020),
        peer("P3", 0.14, 0.015, -0.010),
        peer("P4", 0.16, 0.020, -0.005),
        peer("P5", 0.18, 0.025, 0.000),
        peer("SMALL", 0.99, 0.100, -0.500, eligible=False),
        peer("OWN", 0.50, 0.200, -0.400),
    ]
)


def test_percentile_counts_ties_as_half() -> None:
    row = peer_positions(fund("OWN-A", "OWN"), PEERS).row(0, named=True)
    assert row["peer_count"] == 5
    assert row["fund_return_percentile"] == pytest.approx((2 + 0.5) / 5)
    assert row["volatility_percentile"] == pytest.approx((1 + 0.5) / 5)
    assert row["max_drawdown_percentile"] == pytest.approx((2 + 0.5) / 5)


def test_quartiles_of_the_group() -> None:
    row = peer_positions(fund("OWN-A", "OWN"), PEERS).row(0, named=True)
    assert (row["fund_return_p25"], row["fund_return_median"], row["fund_return_p75"]) == pytest.approx((0.12, 0.14, 0.16))


def test_excludes_ineligible_and_own_class() -> None:
    row = peer_positions(fund("OWN-A", "OWN"), PEERS).row(0, named=True)
    assert row["fund_return_p75"] < 0.5
    assert row["peer_count"] == 5


def test_small_group_has_no_percentile() -> None:
    row = peer_positions(fund("OWN-A", "OWN"), PEERS.filter(pl.col("cnpj") != "P5")).row(0, named=True)
    assert row["peer_count"] == 4
    assert row["fund_return_percentile"] is None


def test_fund_without_twelve_months_has_no_position() -> None:
    row = peer_positions(fund("NEW-A", "NEW", fund_return=None), PEERS).row(0, named=True)
    assert row["peer_count"] == 0
    assert row["fund_return_percentile"] is None


def synthetic_daily(cnpj: str, net_assets: float) -> pl.DataFrame:
    days = business_days(date(2025, 1, 2), 300)
    quotas = compound(1.0, [0.0005, 0.0007] * 149 + [0.0005])
    return pl.DataFrame(
        {
            "cnpj": cnpj,
            "subclass_id": None,
            "date": days,
            "report_type": "CLASSES - FIF",
            "quota_value": [Decimal(f"{q:.12f}") for q in quotas],
            "net_assets": Decimal(f"{net_assets:.2f}"),
        },
        schema_overrides={"subclass_id": pl.String, "quota_value": pl.Decimal(28, 12), "net_assets": pl.Decimal(20, 2)},
    )


def test_peer_table_requires_minimum_net_assets() -> None:
    days = business_days(date(2025, 1, 2), 300)
    daily = pl.concat([synthetic_daily("BIG", MIN_PEER_NET_ASSETS + 1), synthetic_daily("SMALL", MIN_PEER_NET_ASSETS - 1)])
    candidates = pl.DataFrame(
        {"cnpj": ["BIG", "SMALL"], "subclass_id": [None, None], "class_name": ["Big", "Small"], **{k: [v, v] for k, v in GROUP.items()}},
        schema_overrides={"subclass_id": pl.String},
    )
    table = peer_table(daily, candidates, levels_frame(days, 0.05), as_of=days[-1])
    assert dict(table.select("cnpj", "eligible").iter_rows()) == {"BIG": True, "SMALL": False}
    assert table.filter(pl.col("cnpj") == "BIG")["fund_return"].item() is not None
