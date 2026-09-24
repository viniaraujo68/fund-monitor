import polars as pl

from fund_monitor.validation import ensure_unique

NORMAL_STATUS = "Em Funcionamento Normal"
FIF_CLASS_TYPE = "Classes de Cotas de Fundos FIF"
GENERAL_PUBLIC = "Público Geral"
SERIES_KEY = ["cnpj", "subclass_id"]


def is_active_fif() -> pl.Expr:
    return (
        (pl.col("fund_status") == NORMAL_STATUS)
        & (pl.col("class_status") == NORMAL_STATUS)
        & (pl.col("subclass_status").is_null() | (pl.col("subclass_status") == NORMAL_STATUS))
        & (pl.col("class_type") == FIF_CLASS_TYPE)
    )


def is_managed_by(manager_cnpj: str) -> pl.Expr:
    return pl.col("manager_cnpjs").list.contains(manager_cnpj)


def select_manager_series(registry: pl.DataFrame, manager_cnpj: str) -> pl.DataFrame:
    series = registry.filter(is_active_fif(), is_managed_by(manager_cnpj))
    ensure_unique(series, SERIES_KEY, "manager series")
    return series


def select_monitored_series(registry: pl.DataFrame, manager_cnpj: str) -> pl.DataFrame:
    return select_manager_series(registry, manager_cnpj).filter(pl.col("exclusive").not_())
