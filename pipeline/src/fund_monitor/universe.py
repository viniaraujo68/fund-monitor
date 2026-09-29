import logging
from collections.abc import Collection

import polars as pl

from fund_monitor.calc.series import SERIES_KEY
from fund_monitor.validation import ensure_unique

logger = logging.getLogger(__name__)

NORMAL_STATUS = "Em Funcionamento Normal"
FIF_CLASS_TYPE = "Classes de Cotas de Fundos FIF"
GENERAL_PUBLIC = "Público Geral"
REPORTED_COLUMN = "subclass_reported"
STRUCTURAL_MARKERS = ("VEÍCULO ESPECIAL", "FIFE")


def is_structural_vehicle(class_name: str) -> bool:
    return any(marker in class_name for marker in STRUCTURAL_MARKERS)


def is_structural() -> pl.Expr:
    return pl.col("class_name").map_elements(is_structural_vehicle, return_dtype=pl.Boolean)


def is_active_class() -> pl.Expr:
    return (
        (pl.col("fund_status") == NORMAL_STATUS)
        & (pl.col("class_status") == NORMAL_STATUS)
        & (pl.col("class_type") == FIF_CLASS_TYPE)
    )


def is_active_fif() -> pl.Expr:
    return is_active_class() & (pl.col("subclass_status").is_null() | (pl.col("subclass_status") == NORMAL_STATUS))


def consensus(column: str) -> pl.Expr:
    return pl.when(pl.col(column).n_unique() == 1).then(pl.col(column).first()).alias(column)


def mark_reported_subclasses(registry: pl.DataFrame, reported: Collection[str]) -> pl.DataFrame:
    return registry.with_columns(
        pl.col("subclass_id").is_in(list(reported)).fill_null(False).alias(REPORTED_COLUMN)
    )


def waiting_classes(registry: pl.DataFrame) -> pl.DataFrame:
    publishing = (pl.col("subclass_status") == NORMAL_STATUS) & pl.col(REPORTED_COLUMN)
    return (
        registry.filter(is_active_class(), pl.col("subclass_id").is_not_null())
        .group_by("class_registry_id")
        .agg(publishing.any().alias("has_publishing_subclass"))
        .filter(pl.col("has_publishing_subclass").not_())
        .select("class_registry_id")
    )


def transition_classes(registry: pl.DataFrame, waiting: pl.DataFrame) -> pl.DataFrame:
    pending = registry.filter(is_active_class(), pl.col("subclass_id").is_not_null()).join(waiting, on="class_registry_id")
    agreed = pending.group_by("class_registry_id").agg(
        consensus("exclusive"), consensus("target_audience"), consensus("condominium")
    )
    subclass_columns = ["subclass_id", "subclass_name", "subclass_status", REPORTED_COLUMN]
    return (
        pending.sort("class_registry_id", "subclass_id")
        .unique("class_registry_id", keep="first", maintain_order=True)
        .drop("exclusive", "target_audience", "condominium")
        .join(agreed, on="class_registry_id")
        .with_columns(pl.lit(None, dtype=registry.schema[c]).alias(c) for c in subclass_columns)
        .select(registry.columns)
    )


def active_series(registry: pl.DataFrame) -> pl.DataFrame:
    waiting = waiting_classes(registry)
    operational = registry.filter(is_active_fif()).join(waiting, on="class_registry_id", how="anti")
    return pl.concat([operational, transition_classes(registry, waiting)])


def is_managed_by(manager_cnpj: str) -> pl.Expr:
    return pl.col("manager_cnpjs").list.contains(manager_cnpj)


def select_manager_series(registry: pl.DataFrame, manager_cnpj: str) -> pl.DataFrame:
    series = active_series(registry).filter(is_managed_by(manager_cnpj))
    ensure_unique(series, SERIES_KEY, "manager series")
    return series


def select_monitored_series(registry: pl.DataFrame, manager_cnpj: str) -> pl.DataFrame:
    return select_manager_series(registry, manager_cnpj).filter(pl.col("exclusive").not_())


def select_peer_candidates(registry: pl.DataFrame, anbima_classifications: list[str], target_audience: str) -> pl.DataFrame:
    series = active_series(registry)
    ambiguous = series.filter(pl.struct(SERIES_KEY).is_duplicated())
    if ambiguous.height:
        logger.warning("peers: %d active series share a (cnpj, subclass_id) key and are left out", ambiguous.height)
    return series.filter(
        pl.struct(SERIES_KEY).is_duplicated().not_(),
        pl.col("exclusive").not_(),
        pl.col("target_audience") == target_audience,
        pl.col("anbima_classification").is_in(anbima_classifications),
    )


def select_peer_universe(registry: pl.DataFrame, manager_cnpj: str) -> pl.DataFrame:
    monitored = select_monitored_series(registry, manager_cnpj).filter(pl.col("target_audience") == GENERAL_PUBLIC)
    classifications = monitored["anbima_classification"].drop_nulls().unique().sort().to_list()
    return select_peer_candidates(registry, classifications, GENERAL_PUBLIC)
