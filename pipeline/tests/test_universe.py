from datetime import date
from decimal import Decimal

import polars as pl

from fund_monitor.calc.peers import peer_positions
from fund_monitor.calc.series import quota_series, series_id
from fund_monitor.universe import (
    GENERAL_PUBLIC,
    NORMAL_STATUS,
    mark_reported_subclasses,
    select_monitored_series,
    select_peer_universe,
)

MANAGER = "68622174000120"
OTHER_MANAGER = "11111111000111"
FIF = "Classes de Cotas de Fundos FIF"
FIXED_INCOME = "Renda Fixa Duração Livre Crédito Livre"
EQUITY = "Ações Livre"
MULTI_ASSET = "Multimercados Livre"
REGISTRY_SCHEMA = {
    "cnpj": pl.String,
    "subclass_id": pl.String,
    "class_registry_id": pl.String,
    "class_name": pl.String,
    "subclass_name": pl.String,
    "fund_status": pl.String,
    "class_status": pl.String,
    "subclass_status": pl.String,
    "class_type": pl.String,
    "anbima_classification": pl.String,
    "condominium": pl.String,
    "exclusive": pl.Boolean,
    "target_audience": pl.String,
    "manager_cnpjs": pl.List(pl.String),
}


def series(cnpj: str, class_id: str, **overrides: object) -> dict:
    row = {
        "cnpj": cnpj,
        "subclass_id": None,
        "class_registry_id": class_id,
        "class_name": f"CLASS {class_id}",
        "subclass_name": None,
        "fund_status": NORMAL_STATUS,
        "class_status": NORMAL_STATUS,
        "subclass_status": None,
        "class_type": FIF,
        "anbima_classification": FIXED_INCOME,
        "condominium": "Aberto",
        "exclusive": False,
        "target_audience": GENERAL_PUBLIC,
        "manager_cnpjs": [OTHER_MANAGER],
    }
    return row | overrides


def subclass(cnpj: str, class_id: str, subclass_id: str, **overrides: object) -> dict:
    names = {"subclass_id": subclass_id, "subclass_name": f"SUBCLASS {subclass_id}", "subclass_status": NORMAL_STATUS}
    return series(cnpj, class_id, **names, **overrides)


def registry(rows: list[dict], reported: set[str] | None = None) -> pl.DataFrame:
    frame = pl.DataFrame(rows, schema=REGISTRY_SCHEMA)
    return mark_reported_subclasses(frame, frame["subclass_id"].drop_nulls() if reported is None else reported)


def keys(frame: pl.DataFrame) -> set[tuple[str, str | None]]:
    return set(frame.select("cnpj", "subclass_id").iter_rows())


MANAGER_ROWS = [
    series("M0000000000001", "1", manager_cnpjs=[MANAGER]),
    series("M0000000000002", "2", manager_cnpjs=[MANAGER], anbima_classification=EQUITY),
    series("M0000000000003", "3", manager_cnpjs=[MANAGER], anbima_classification=MULTI_ASSET, target_audience="Profissional"),
    series("M0000000000004", "4", manager_cnpjs=[MANAGER], anbima_classification="Ações Dividendos", exclusive=True),
    series("M0000000000005", "5", manager_cnpjs=[MANAGER], anbima_classification=None),
]


def test_peer_universe_matches_classification_audience_and_status() -> None:
    rows = [
        *MANAGER_ROWS,
        series("P0000000000001", "11"),
        series("P0000000000002", "12", anbima_classification=EQUITY),
        series("X0000000000001", "21", exclusive=True),
        series("X0000000000002", "22", target_audience="Qualificado"),
        series("X0000000000003", "23", anbima_classification=MULTI_ASSET),
        series("X0000000000004", "24", anbima_classification="Ações Dividendos"),
        series("X0000000000005", "25", class_status="Cancelada"),
        series("X0000000000006", "26", fund_status="Cancelado"),
        series("X0000000000007", "27", class_type="Classes de Cotas de Fundos FII"),
        series("X0000000000008", "28", anbima_classification=None),
        series("X0000000000009", "29", exclusive=None),
    ]
    assert keys(select_peer_universe(registry(rows), MANAGER)) == {
        ("M0000000000001", None),
        ("M0000000000002", None),
        ("P0000000000001", None),
        ("P0000000000002", None),
    }


def test_peer_universe_leaves_out_a_cnpj_shared_by_two_active_classes() -> None:
    rows = [
        *MANAGER_ROWS,
        series("P0000000000001", "11"),
        series("D0000000000001", "12"),
        series("D0000000000001", "13"),
        series("D0000000000002", "14"),
        series("D0000000000002", "15", exclusive=True),
    ]
    peers = select_peer_universe(registry(rows), MANAGER)
    assert keys(peers) == {("M0000000000001", None), ("M0000000000002", None), ("P0000000000001", None)}
    assert peers.select("cnpj", "subclass_id").is_duplicated().sum() == 0


def test_own_class_and_sister_subclasses_are_not_peers() -> None:
    rows = [
        subclass("M0000000000001", "1", "SUBA", manager_cnpjs=[MANAGER]),
        subclass("M0000000000001", "1", "SUBB", manager_cnpjs=[MANAGER]),
        *(series(f"P000000000000{number}", f"1{number}") for number in range(1, 6)),
    ]
    universe = select_peer_universe(registry(rows), MANAGER)
    assert {"SUBA", "SUBB"} <= set(universe["subclass_id"].drop_nulls())
    metrics = {"fund_return": 0.1, "volatility": 0.01, "max_drawdown": -0.01}
    constants = {name: pl.lit(value) for name, value in metrics.items()}
    peers = universe.with_columns(series_id(), eligible=pl.lit(True), **constants)
    subject = peers.filter(pl.col("subclass_id") == "SUBA")
    assert peer_positions(subject, peers).row(0, named=True)["peer_count"] == 5


CLASS_WITH_NEW_SUBCLASSES = [
    subclass("M0000000000001", "1", "SUBA", manager_cnpjs=[MANAGER]),
    subclass("M0000000000001", "1", "SUBB", manager_cnpjs=[MANAGER]),
]


def class_rows(days: list[date]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "cnpj": ["M0000000000001"] * len(days),
            "subclass_id": [None] * len(days),
            "date": days,
            "quota_value": [Decimal("1.000000000000") + Decimal(position) / 1000 for position in range(len(days))],
        },
        schema={"cnpj": pl.String, "subclass_id": pl.String, "date": pl.Date, "quota_value": pl.Decimal(28, 12)},
    )


def test_class_stays_monitored_until_an_operational_subclass_reports() -> None:
    waiting = select_monitored_series(registry(CLASS_WITH_NEW_SUBCLASSES, reported=set()), MANAGER)
    assert keys(waiting) == {("M0000000000001", None)}
    daily = class_rows([date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)])
    assert quota_series(daily, waiting).height == 3


def test_class_with_disagreeing_unreported_subclasses_is_not_monitored() -> None:
    rows = [{**row, "exclusive": row["subclass_id"] == "SUBB"} for row in CLASS_WITH_NEW_SUBCLASSES]
    assert keys(select_monitored_series(registry(rows, reported=set()), MANAGER)) == set()


def test_subclasses_replace_the_class_once_one_of_them_reports() -> None:
    monitored = select_monitored_series(registry(CLASS_WITH_NEW_SUBCLASSES, reported={"SUBB"}), MANAGER)
    assert keys(monitored) == {("M0000000000001", "SUBA"), ("M0000000000001", "SUBB")}


def test_a_reported_pre_operational_subclass_does_not_end_the_wait() -> None:
    pre_operational = {"subclass_status": "Fase Pré-Operacional"}
    rows = [row | pre_operational if row["subclass_id"] == "SUBB" else row for row in CLASS_WITH_NEW_SUBCLASSES]
    monitored = select_monitored_series(registry(rows, reported={"SUBB"}), MANAGER)
    assert keys(monitored) == {("M0000000000001", None)}
