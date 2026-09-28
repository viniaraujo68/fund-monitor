import shutil
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from fund_monitor import config
from fund_monitor.collect import cvm_registry
from fund_monitor.collect.cvm_registry import RegistryTables, build_registry, read_registry_zip
from fund_monitor.universe import mark_reported_subclasses, select_manager_series, select_monitored_series

SAMPLE_ZIP = Path(__file__).parent / "fixtures" / "registro_fundo_classe_sample.zip"
ICATU_VANGUARDA = "68622174000120"
DIVIDENDS_CNPJ = "08279304000141"


@pytest.fixture(scope="module")
def tables() -> RegistryTables:
    return read_registry_zip(SAMPLE_ZIP)


@pytest.fixture(scope="module")
def registry(tables: RegistryTables) -> pl.DataFrame:
    built = build_registry(tables)
    return mark_reported_subclasses(built, built["subclass_id"].drop_nulls())


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
    assert registry.schema["exclusive"] == pl.Boolean


def test_unused_columns_are_not_parsed(tables: RegistryTables) -> None:
    classes = tables.classes.with_columns(
        Tributacao_Longo_Prazo=pl.lit("Sim"),
        Patrimonio_Liquido=pl.lit("1,5"),
        Data_Patrimonio_Liquido=pl.lit("31/08/2026"),
        Data_Inicio=pl.lit("2026-02-30"),
    )
    subclasses = tables.subclasses.with_columns(Data_Inicio=pl.lit("2026-02-30"))
    registry = build_registry(RegistryTables(tables.funds, classes, subclasses))
    assert registry.height == build_registry(tables).height
    assert not {"class_start_date", "subclass_start_date", "long_term_taxation", "class_net_assets", "class_net_assets_date"} & set(registry.columns)


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


def with_subclass_status(registry: pl.DataFrame, cnpj: str, status: str, exclusive: bool | None = None) -> pl.DataFrame:
    target = pl.col("cnpj") == cnpj
    changed = registry.with_columns(pl.when(target).then(pl.lit(status)).otherwise(pl.col("subclass_status")).alias("subclass_status"))
    if exclusive is not None:
        changed = changed.with_columns(
            pl.when(target).then(pl.lit(exclusive)).otherwise(pl.col("exclusive")).alias("exclusive"),
            pl.when(target).then(pl.lit("Público Geral")).otherwise(pl.col("target_audience")).alias("target_audience"),
        )
    return changed


def test_class_waiting_for_its_subclasses_is_monitored_as_the_class(registry: pl.DataFrame) -> None:
    waiting = with_subclass_status(registry, DIVIDENDS_CNPJ, "Fase Pré-Operacional", exclusive=False)
    monitored = select_monitored_series(waiting, ICATU_VANGUARDA)
    assert (DIVIDENDS_CNPJ, None) in series_keys(monitored)
    assert not any(key[0] == DIVIDENDS_CNPJ and key[1] for key in series_keys(monitored))
    row = monitored.filter(pl.col("cnpj") == DIVIDENDS_CNPJ).row(0, named=True)
    assert (row["exclusive"], row["target_audience"]) == (False, "Público Geral")


def test_waiting_class_with_disagreeing_subclasses_is_not_monitored(registry: pl.DataFrame) -> None:
    waiting = with_subclass_status(registry, DIVIDENDS_CNPJ, "Fase Pré-Operacional")
    assert (DIVIDENDS_CNPJ, None) in series_keys(select_manager_series(waiting, ICATU_VANGUARDA))
    assert DIVIDENDS_CNPJ not in {key[0] for key in series_keys(select_monitored_series(waiting, ICATU_VANGUARDA))}


def test_class_with_an_operational_subclass_is_not_duplicated(registry: pl.DataFrame) -> None:
    assert (DIVIDENDS_CNPJ, None) not in series_keys(select_manager_series(registry, ICATU_VANGUARDA))


def test_new_snapshot_replaces_the_older_ones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "REGISTRY_RAW_DIR", tmp_path)
    downloads = []

    def fake_download(url: str, destination: Path) -> Path:
        downloads.append(destination.name)
        shutil.copy(SAMPLE_ZIP, destination)
        return destination

    monkeypatch.setattr(cvm_registry, "download_file", fake_download)
    for name in ("registro_fundo_classe_20260925.zip", "registro_fundo_classe_20260926.zip", "notes.txt"):
        (tmp_path / name).write_bytes(b"old")
    registry = cvm_registry.collect_registry(date(2026, 9, 28))
    cvm_registry.collect_registry(date(2026, 9, 28))
    assert downloads == ["registro_fundo_classe_20260928.zip"]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["notes.txt", "registro_fundo_classe_20260928.zip"]
    assert registry.height == 9
