import io
import logging
import zipfile
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import httpx
import polars as pl

from fund_monitor import config
from fund_monitor.collect.download import download_if_changed

logger = logging.getLogger(__name__)

SEPARATOR = ";"
CNPJ_FIELD = "CNPJ_FUNDO_CLASSE"
MONEY = pl.Decimal(20, 2)
QUOTA = pl.Decimal(28, 12)
EXPECTED_COLUMNS = [
    "TP_FUNDO_CLASSE",
    "CNPJ_FUNDO_CLASSE",
    "ID_SUBCLASSE",
    "DT_COMPTC",
    "VL_TOTAL",
    "VL_QUOTA",
    "VL_PATRIM_LIQ",
    "CAPTC_DIA",
    "RESG_DIA",
    "NR_COTST",
]


def months_between(start: date, end: date) -> list[date]:
    months = []
    current = date(start.year, start.month, 1)
    while current <= end:
        months.append(current)
        current = date(current.year + current.month // 12, current.month % 12 + 1, 1)
    return months


def daily_url(month: date) -> str:
    return config.CVM_DAILY_URL.format(yyyymm=f"{month:%Y%m}")


def daily_raw_path(month: date) -> Path:
    return config.DAILY_RAW_DIR / f"inf_diario_fi_{month:%Y%m}.zip"


def daily_parquet_path(month: date) -> Path:
    return config.DAILY_PARQUET_DIR / f"{month:%Y%m}.parquet"


def mask_cnpj(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def filter_lines(lines: Iterable[str], cnpjs: set[str]) -> str:
    iterator = iter(lines)
    header = next(iterator)
    columns = header.rstrip("\r\n").split(SEPARATOR)
    if columns != EXPECTED_COLUMNS:
        raise ValueError(f"unexpected daily report header: {columns}")
    position = columns.index(CNPJ_FIELD)
    masked = {mask_cnpj(cnpj) for cnpj in cnpjs} | cnpjs
    kept = [line for line in iterator if line.split(SEPARATOR, position + 1)[position] in masked]
    return header + "".join(kept)


def read_daily_zip(path: Path, cnpjs: set[str]) -> pl.DataFrame:
    with zipfile.ZipFile(path) as archive:
        (member,) = archive.namelist()
        with archive.open(member) as raw, io.TextIOWrapper(raw, encoding="latin1") as text:
            content = filter_lines(text, cnpjs)
    frame = pl.read_csv(io.StringIO(content), separator=SEPARATOR, infer_schema=False, quote_char=None)
    return normalize_daily(frame)


def normalize_daily(frame: pl.DataFrame) -> pl.DataFrame:
    normalized = frame.select(
        pl.col("CNPJ_FUNDO_CLASSE").str.replace_all(r"\D", "").alias("cnpj"),
        pl.col("ID_SUBCLASSE").alias("subclass_id"),
        pl.col("DT_COMPTC").str.to_date("%Y-%m-%d").alias("date"),
        pl.col("TP_FUNDO_CLASSE").alias("report_type"),
        pl.col("VL_QUOTA").cast(QUOTA, strict=True).alias("quota_value"),
        pl.col("VL_PATRIM_LIQ").cast(MONEY, strict=True).alias("net_assets"),
        pl.col("VL_TOTAL").cast(MONEY, strict=True).alias("total_assets"),
        pl.col("CAPTC_DIA").cast(MONEY, strict=True).alias("inflows"),
        pl.col("RESG_DIA").cast(MONEY, strict=True).alias("outflows"),
        pl.col("NR_COTST").cast(pl.Int64, strict=True).alias("shareholders"),
    )
    malformed = normalized.filter(pl.col("cnpj").str.len_chars() != 14)
    if malformed.height:
        raise ValueError(f"daily report has {malformed.height} rows with a malformed CNPJ")
    return normalized.sort("cnpj", "subclass_id", "date", nulls_last=False)


def collect_month(month: date, cnpjs: set[str], reference_month: date) -> pl.DataFrame | None:
    raw_path = daily_raw_path(month)
    try:
        download_if_changed(daily_url(month), raw_path)
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404 and month == reference_month:
            logger.warning("daily report for %s is not published yet", f"{month:%Y-%m}")
            return None
        raise
    parquet_path = daily_parquet_path(month)
    frame = read_daily_zip(raw_path, cnpjs)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(parquet_path, compression="zstd")
    logger.info("daily %s: %d rows, %d classes", f"{month:%Y-%m}", frame.height, frame["cnpj"].n_unique())
    return frame


def collect_daily(start: date, reference_date: date, cnpjs: set[str]) -> list[date]:
    reference_month = date(reference_date.year, reference_date.month, 1)
    collected = []
    for month in months_between(start, reference_month):
        if collect_month(month, cnpjs, reference_month) is not None:
            collected.append(month)
    return collected
