import shutil
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import polars as pl
import pytest

from fund_monitor import config
from fund_monitor.collect import cvm_daily

SAMPLE_ZIP = Path(__file__).parent / "fixtures" / "inf_diario_fi_202608_sample.zip"
SELECTED = {"04820026000137", "08279304000141", "64026956000145"}
AUGUST = date(2026, 8, 1)


@pytest.fixture(scope="module")
def daily() -> pl.DataFrame:
    return cvm_daily.read_daily_zip(SAMPLE_ZIP, SELECTED)


@pytest.fixture
def data_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config, "DAILY_RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "DAILY_PARQUET_DIR", tmp_path / "parquet")
    return tmp_path


def fake_download(url: str, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(SAMPLE_ZIP, destination)
    return True


def not_found(url: str, destination: Path) -> bool:
    request = httpx.Request("HEAD", url)
    raise httpx.HTTPStatusError("not found", request=request, response=httpx.Response(404, request=request))


def test_months_between_crosses_year() -> None:
    assert cvm_daily.months_between(date(2024, 11, 15), date(2025, 2, 1)) == [
        date(2024, 11, 1),
        date(2024, 12, 1),
        date(2025, 1, 1),
        date(2025, 2, 1),
    ]


def test_mask_cnpj() -> None:
    assert cvm_daily.mask_cnpj("08279304000141") == "08.279.304/0001-41"


def test_keeps_only_selected_cnpjs(daily: pl.DataFrame) -> None:
    assert set(daily["cnpj"].unique()) == SELECTED
    assert daily.height == 44


def test_keeps_subclass_rows_apart(daily: pl.DataFrame) -> None:
    counts = daily.group_by("cnpj", "subclass_id").len().sort("cnpj", "subclass_id", nulls_last=False).rows()
    assert counts == [
        ("04820026000137", None, 11),
        ("08279304000141", "2NPXA1767643549", 11),
        ("08279304000141", "9WCV01767643284", 11),
        ("64026956000145", None, 4),
        ("64026956000145", "QFJB91787329596", 7),
    ]


def read_raw_sample() -> pl.DataFrame:
    with zipfile.ZipFile(SAMPLE_ZIP) as archive:
        return pl.read_csv(archive.read("inf_diario_fi_202608.csv"), separator=";", infer_schema=False)


def test_preserves_decimal_precision(daily: pl.DataFrame) -> None:
    raw = read_raw_sample().filter(
        pl.col("CNPJ_FUNDO_CLASSE") == "04.820.026/0001-37", pl.col("DT_COMPTC") == "2026-08-31"
    )
    row = daily.filter(pl.col("cnpj") == "04820026000137", pl.col("date") == date(2026, 8, 31))
    assert row["quota_value"].item() == Decimal(raw["VL_QUOTA"].item())
    assert row["net_assets"].item() == Decimal(raw["VL_PATRIM_LIQ"].item())
    assert daily.schema["quota_value"] == pl.Decimal(28, 12)


def test_rejects_unexpected_header() -> None:
    with pytest.raises(ValueError, match="unexpected daily report header"):
        cvm_daily.filter_lines(["CNPJ_FUNDO;DT_COMPTC\n"], SELECTED)


def test_collect_month_writes_parquet(data_dirs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cvm_daily, "download_if_changed", fake_download)
    frame = cvm_daily.collect_month(AUGUST, SELECTED, reference_month=date(2026, 9, 1))
    written = pl.read_parquet(data_dirs / "parquet" / "202608.parquet")
    assert frame is not None
    assert written.equals(frame)


def test_unpublished_reference_month_is_skipped(data_dirs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cvm_daily, "download_if_changed", not_found)
    assert cvm_daily.collect_month(AUGUST, SELECTED, reference_month=AUGUST) is None


def test_missing_past_month_fails(data_dirs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cvm_daily, "download_if_changed", not_found)
    with pytest.raises(httpx.HTTPStatusError):
        cvm_daily.collect_month(AUGUST, SELECTED, reference_month=date(2026, 9, 1))
