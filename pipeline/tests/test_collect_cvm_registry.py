from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from fund_monitor.collect.cvm_registry import RegistryTables, build_registry, read_registry_zip
from fund_monitor.universe import select_manager_series, select_monitored_series

SAMPLE_ZIP = Path(__file__).parent / "fixtures" / "registro_fundo_classe_sample.zip"
ICATU_VANGUARDA = "68622174000120"
DIVIDENDS_CNPJ = "08279304000141"


@pytest.fixture(scope="module")
def tables() -> RegistryTables:
    return read_registry_zip(SAMPLE_ZIP)


@pytest.fixture(scope="module")
def registry(tables: RegistryTables) -> pl.DataFrame:
    return build_registry(tables)


def series_keys(frame: pl.DataFrame) -> set[tuple[str, str | None]]:
    return set(frame.select("cnpj", "subclass_id").iter_rows())


def test_reads_literal_quotes_in_names(tables: RegistryTables) -> None:
    names = tables.subclasses["Denominacao_Social"].to_list()
    assert any('SUBCLASSE  "A"' in name for name in names)


def test_class_with_subclasses_yields_one_series_per_subclass(registry: pl.DataFrame) -> None:
    dividends = registry.filter(pl.col("cnpj") == DIVIDENDS_CNPJ).sort("subclass_id")
    assert dividends.select("subclass_id", "exclusive", "target_audience").rows() == [
        ("2NPXA1767643549", True, "Profissional"),
        ("9WCV01767643284", False, "Público Geral"),
    ]


def test_class_without_subclasses_keeps_class_attributes(registry: pl.DataFrame) -> None:
    row = registry.filter(pl.col("cnpj") == "04820026000137").to_dicts()
    assert len(row) == 1
    assert row[0]["subclass_id"] is None
    assert row[0]["exclusive"] is False
    assert row[0]["target_audience"] == "Público Geral"
    assert row[0]["anbima_classification"] == "Multimercados Dinâmico"


def test_co_managed_fund_is_not_duplicated(registry: pl.DataFrame) -> None:
    row = registry.filter(pl.col("fund_registry_id") == "1846").to_dicts()
    assert len(row) == 1
    assert row[0]["manager_cnpjs"] == ["38183509000190", ICATU_VANGUARDA]


def test_class_repeated_per_custodian_collapses(tables: RegistryTables, registry: pl.DataFrame) -> None:
    assert tables.classes.filter(pl.col("ID_Registro_Classe") == "18730").height == 2
    assert registry.filter(pl.col("class_registry_id") == "18730").height == 1


def test_types(registry: pl.DataFrame) -> None:
    assert registry.schema["class_net_assets"] == pl.Decimal(20, 2)
    assert registry.schema["class_start_date"] == pl.Date
    assert registry.schema["exclusive"] == pl.Boolean
    row = registry.filter(pl.col("cnpj") == "04820026000137").row(0, named=True)
    assert isinstance(row["class_net_assets"], Decimal)


def test_unknown_exclusive_flag_is_rejected(tables: RegistryTables) -> None:
    classes = tables.classes.with_columns(Exclusivo=pl.lit("X"))
    with pytest.raises(pl.exceptions.InvalidOperationError):
        build_registry(RegistryTables(tables.funds, classes, tables.subclasses))


def test_duplicated_subclass_is_rejected(tables: RegistryTables) -> None:
    changed = tables.subclasses.with_columns(Denominacao_Social=pl.lit("OTHER"))
    subclasses = pl.concat([tables.subclasses, changed.head(1)])
    with pytest.raises(ValueError, match="registro_subclasse.csv"):
        build_registry(RegistryTables(tables.funds, tables.classes, subclasses))


def test_manager_series_excludes_other_managers_and_non_fif(registry: pl.DataFrame) -> None:
    assert series_keys(select_manager_series(registry, ICATU_VANGUARDA)) == {
        ("04820026000137", None),
        ("12053727000116", None),
        (DIVIDENDS_CNPJ, "2NPXA1767643549"),
        (DIVIDENDS_CNPJ, "9WCV01767643284"),
    }


def test_monitored_series_excludes_exclusive(registry: pl.DataFrame) -> None:
    assert series_keys(select_monitored_series(registry, ICATU_VANGUARDA)) == {
        ("04820026000137", None),
        (DIVIDENDS_CNPJ, "9WCV01767643284"),
    }
