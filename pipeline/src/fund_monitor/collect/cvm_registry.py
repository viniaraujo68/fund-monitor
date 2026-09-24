import logging
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl

from fund_monitor import config
from fund_monitor.collect.download import download_file
from fund_monitor.validation import ensure_unique

logger = logging.getLogger(__name__)

FUND_FILE = "registro_fundo.csv"
CLASS_FILE = "registro_classe.csv"
SUBCLASS_FILE = "registro_subclasse.csv"

MONEY = pl.Decimal(20, 2)
YES_NO = {"S": True, "N": False}
LONG_TERM_TAXATION = {"S": True, "N": False, "N/A": None}

FUND_COLUMNS = {
    "ID_Registro_Fundo": "fund_registry_id",
    "CNPJ_Fundo": "fund_cnpj",
    "Denominacao_Social": "fund_name",
    "Situacao": "fund_status",
    "Administrador": "administrator_name",
}
MANAGER_COLUMNS = {
    "ID_Registro_Fundo": "fund_registry_id",
    "CPF_CNPJ_Gestor": "manager_cnpj",
    "Gestor": "manager_name",
}
CLASS_COLUMNS = {
    "ID_Registro_Fundo": "fund_registry_id",
    "ID_Registro_Classe": "class_registry_id",
    "CNPJ_Classe": "cnpj",
    "Denominacao_Social": "class_name",
    "Situacao": "class_status",
    "Data_Inicio": "class_start_date",
    "Tipo_Classe": "class_type",
    "Classificacao": "cvm_classification",
    "Classificacao_Anbima": "anbima_classification",
    "Indicador_Desempenho": "performance_benchmark",
    "Forma_Condominio": "class_condominium",
    "Exclusivo": "class_exclusive",
    "Publico_Alvo": "class_target_audience",
    "Tributacao_Longo_Prazo": "long_term_taxation",
    "Patrimonio_Liquido": "class_net_assets",
    "Data_Patrimonio_Liquido": "class_net_assets_date",
}
SUBCLASS_COLUMNS = {
    "ID_Registro_Classe": "class_registry_id",
    "ID_Subclasse": "subclass_id",
    "Denominacao_Social": "subclass_name",
    "Situacao": "subclass_status",
    "Data_Inicio": "subclass_start_date",
    "Forma_Condominio": "subclass_condominium",
    "Exclusivo": "subclass_exclusive",
    "Publico_Alvo": "subclass_target_audience",
}


@dataclass(frozen=True)
class RegistryTables:
    funds: pl.DataFrame
    classes: pl.DataFrame
    subclasses: pl.DataFrame


def read_cvm_csv(content: bytes) -> pl.DataFrame:
    return pl.read_csv(content, separator=";", encoding="latin1", infer_schema=False, quote_char=None)


def read_registry_zip(path: Path) -> RegistryTables:
    with zipfile.ZipFile(path) as archive:
        return RegistryTables(
            funds=read_cvm_csv(archive.read(FUND_FILE)),
            classes=read_cvm_csv(archive.read(CLASS_FILE)),
            subclasses=read_cvm_csv(archive.read(SUBCLASS_FILE)),
        )


def select_renamed(frame: pl.DataFrame, columns: dict[str, str]) -> pl.DataFrame:
    return frame.select(pl.col(source).alias(target) for source, target in columns.items())


def parse_date(column: str) -> pl.Expr:
    return pl.col(column).str.to_date("%Y-%m-%d")


def normalize_funds(funds: pl.DataFrame) -> pl.DataFrame:
    attributes = select_renamed(funds, FUND_COLUMNS).unique()
    ensure_unique(attributes, ["fund_registry_id"], FUND_FILE)
    managers = (
        select_renamed(funds, MANAGER_COLUMNS)
        .drop_nulls("manager_cnpj")
        .unique()
        .sort("fund_registry_id", "manager_cnpj")
        .group_by("fund_registry_id", maintain_order=True)
        .agg(manager_cnpjs=pl.col("manager_cnpj"), manager_names=pl.col("manager_name"))
    )
    return attributes.join(managers, on="fund_registry_id", how="left", validate="1:1")


def normalize_classes(classes: pl.DataFrame) -> pl.DataFrame:
    normalized = select_renamed(classes, CLASS_COLUMNS).unique()
    ensure_unique(normalized, ["class_registry_id"], CLASS_FILE)
    return normalized


def normalize_subclasses(subclasses: pl.DataFrame) -> pl.DataFrame:
    normalized = select_renamed(subclasses, SUBCLASS_COLUMNS).unique()
    ensure_unique(normalized, ["subclass_id"], SUBCLASS_FILE)
    return normalized


def build_registry(tables: RegistryTables) -> pl.DataFrame:
    funds = normalize_funds(tables.funds)
    classes = normalize_classes(tables.classes)
    subclasses = normalize_subclasses(tables.subclasses)
    joined = classes.join(funds, on="fund_registry_id", how="left", validate="m:1").join(
        subclasses, on="class_registry_id", how="left", validate="1:m"
    )
    registry = joined.select(
        "cnpj",
        "subclass_id",
        "class_registry_id",
        "fund_registry_id",
        "fund_cnpj",
        "fund_name",
        "class_name",
        "subclass_name",
        "fund_status",
        "class_status",
        "subclass_status",
        parse_date("class_start_date"),
        parse_date("subclass_start_date"),
        "class_type",
        "cvm_classification",
        "anbima_classification",
        "performance_benchmark",
        pl.coalesce("subclass_condominium", "class_condominium").alias("condominium"),
        pl.coalesce("subclass_exclusive", "class_exclusive")
        .replace_strict(YES_NO, return_dtype=pl.Boolean)
        .alias("exclusive"),
        pl.coalesce("subclass_target_audience", "class_target_audience").alias("target_audience"),
        pl.col("long_term_taxation").replace_strict(LONG_TERM_TAXATION, return_dtype=pl.Boolean),
        pl.col("class_net_assets").cast(MONEY, strict=True),
        parse_date("class_net_assets_date"),
        "administrator_name",
        "manager_cnpjs",
        "manager_names",
    ).sort("cnpj", "subclass_id", "class_registry_id", nulls_last=False)
    ensure_unique(registry, ["class_registry_id", "subclass_id"], "registry")
    return registry


def registry_raw_path(reference_date: date) -> Path:
    return config.REGISTRY_RAW_DIR / f"registro_fundo_classe_{reference_date:%Y%m%d}.zip"


def collect_registry(reference_date: date) -> pl.DataFrame:
    raw_path = registry_raw_path(reference_date)
    if not raw_path.exists():
        download_file(config.CVM_REGISTRY_URL, raw_path)
    registry = build_registry(read_registry_zip(raw_path))
    config.REGISTRY_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    registry.write_parquet(config.REGISTRY_PARQUET, compression="zstd")
    logger.info("registry: %d series written to %s", registry.height, config.REGISTRY_PARQUET)
    return registry
