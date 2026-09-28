import io
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import polars as pl

from fund_monitor import config
from fund_monitor.collect.numbers import INDEX_LEVEL, RATE, parse_brazilian_number
from fund_monitor.validation import ensure_unique

logger = logging.getLogger(__name__)

HEADER_PREFIX = "Índice;"
NO_DATA_PREFIX = "Não há dados disponíveis"
SCHEMA = {"index": pl.String, "date": pl.Date, "value": INDEX_LEVEL, "daily_change_pct": RATE}


def weekdays_between(start: date, end: date) -> list[date]:
    days = (start + timedelta(days=offset) for offset in range((end - start).days + 1))
    return [day for day in days if day.weekday() < 5]


def request_form(day: date) -> dict[str, str]:
    return {
        "Tipo": "",
        "DataRef": "",
        "Pai": "ima",
        "escolha": "2",
        "Idioma": "PT",
        "saida": "csv",
        "Dt_Ref_Ver": f"{day:%Y%m%d}",
        "Dt_Ref": f"{day:%d/%m/%Y}",
    }


def raw_path(day: date) -> Path:
    return config.ANBIMA_RAW_DIR / f"{day:%Y%m%d}.csv"


def header_position(lines: list[str]) -> int | None:
    return next((position for position, line in enumerate(lines) if line.startswith(HEADER_PREFIX)), None)


def is_expected_reply(content: bytes) -> bool:
    text = content.decode("latin1")
    return text.startswith(NO_DATA_PREFIX) or header_position(text.splitlines()) is not None


def parse_ima_csv(content: bytes) -> pl.DataFrame:
    lines = content.decode("latin1").splitlines()
    header = header_position(lines)
    if header is None:
        if not is_expected_reply(content):
            raise ValueError(f"unexpected anbima reply: {content[:80]!r}")
        return pl.DataFrame(schema=SCHEMA)
    frame = pl.read_csv(
        io.StringIO("\n".join(lines[header:])), separator=";", infer_schema=False, quote_char=None
    )
    return frame.filter(pl.col("Índice").is_in(config.ANBIMA_INDICES)).select(
        pl.col("Índice").alias("index"),
        pl.col("Data de Referência").str.to_date("%d/%m/%Y").alias("date"),
        parse_brazilian_number("Número Índice").cast(INDEX_LEVEL, strict=True).alias("value"),
        parse_brazilian_number("Variação Diária(%)").cast(RATE, strict=True).alias("daily_change_pct"),
    )


def needs_fetch(day: date, reference_date: date) -> bool:
    path = raw_path(day)
    if not path.exists():
        return True
    content = path.read_bytes()
    if not is_expected_reply(content):
        return True
    is_recent = (reference_date - day).days <= config.ANBIMA_RETRY_EMPTY_DAYS
    return is_recent and parse_ima_csv(content).is_empty()


def fetch_day(client: httpx.Client, day: date) -> None:
    response = client.post(config.ANBIMA_IMA_URL, data=request_form(day))
    response.raise_for_status()
    path = raw_path(day)
    if not is_expected_reply(response.content):
        logger.warning("anbima %s: unexpected reply of %d bytes not saved, retried next run", day, len(response.content))
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)


def read_day(day: date) -> pl.DataFrame:
    path = raw_path(day)
    if not path.exists():
        return pl.DataFrame(schema=SCHEMA)
    frame = parse_ima_csv(path.read_bytes())
    mismatched = frame.filter(pl.col("date") != day)
    if mismatched.height:
        logger.warning("anbima %s: dropping %d rows dated otherwise", day, mismatched.height)
    return frame.filter(pl.col("date") == day)


def collect_ima(start: date, reference_date: date) -> pl.DataFrame:
    days = weekdays_between(start, reference_date - timedelta(days=1))
    pending = [day for day in days if needs_fetch(day, reference_date)]
    logger.info("anbima: %d weekdays in window, %d to fetch", len(days), len(pending))
    with httpx.Client(timeout=60.0) as client:
        for position, day in enumerate(pending):
            if position:
                time.sleep(config.ANBIMA_REQUEST_PAUSE_SECONDS)
            fetch_day(client, day)
    ima = pl.concat([read_day(day) for day in days]).sort("index", "date")
    ensure_unique(ima, ["index", "date"], "anbima ima")
    config.IMA_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    ima.write_parquet(config.IMA_PARQUET, compression="zstd")
    logger.info("anbima: %d rows, %d days, last %s", ima.height, ima["date"].n_unique(), ima["date"].max())
    return ima
