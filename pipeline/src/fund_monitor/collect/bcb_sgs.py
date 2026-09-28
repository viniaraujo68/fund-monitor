import json
import logging
import time
from dataclasses import dataclass
from datetime import date

import httpx
import polars as pl

from fund_monitor import config
from fund_monitor.collect.numbers import RATE
from fund_monitor.validation import ensure_unique

logger = logging.getLogger(__name__)

FETCH_ATTEMPTS = 3
RETRY_PAUSE_SECONDS = 2.0


@dataclass(frozen=True)
class SgsSeries:
    name: str
    series_id: int
    unit: str


SERIES = (SgsSeries("cdi", 12, "percent_per_day"),)


def fetch_series(client: httpx.Client, series: SgsSeries, start: date, end: date) -> bytes:
    response = client.get(
        config.BCB_SGS_URL.format(series_id=series.series_id),
        params={"formato": "json", "dataInicial": f"{start:%d/%m/%Y}", "dataFinal": f"{end:%d/%m/%Y}"},
    )
    response.raise_for_status()
    return response.content


def decode_records(content: bytes) -> list[dict[str, str]] | None:
    try:
        records = json.loads(content)
    except ValueError:
        return None
    is_series = (
        isinstance(records, list)
        and len(records) > 0
        and all(isinstance(record, dict) and "data" in record and "valor" in record for record in records)
    )
    return records if is_series else None


def fetch_records(client: httpx.Client, series: SgsSeries, start: date, end: date) -> tuple[bytes, list[dict[str, str]]]:
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        content = fetch_series(client, series, start, end)
        records = decode_records(content)
        if records is not None:
            return content, records
        logger.warning("bcb %s: attempt %d returned something that is not the series: %r", series.name, attempt, content[:80])
        if attempt < FETCH_ATTEMPTS:
            time.sleep(RETRY_PAUSE_SECONDS)
    raise ValueError(f"bcb {series.name}: the Bacen replied {FETCH_ATTEMPTS} times with something that is not the series")


def parse_series(series: SgsSeries, records: list[dict[str, str]]) -> pl.DataFrame:
    frame = pl.DataFrame(records, schema={"data": pl.String, "valor": pl.String})
    return frame.select(
        pl.lit(series.name).alias("index"),
        pl.col("data").str.to_date("%d/%m/%Y").alias("date"),
        pl.col("valor").cast(RATE, strict=True).alias("value"),
        pl.lit(series.unit).alias("unit"),
    )


def collect_bcb(start: date, end: date) -> pl.DataFrame:
    config.BCB_RAW_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    with httpx.Client(timeout=60.0) as client:
        for series in SERIES:
            content, records = fetch_records(client, series, start, end)
            (config.BCB_RAW_DIR / f"sgs_{series.series_id}.json").write_bytes(content)
            frame = parse_series(series, records)
            logger.info("bcb %s: %d values, last %s", series.name, frame.height, frame["date"].max())
            frames.append(frame)
    indices = pl.concat(frames).sort("index", "date")
    ensure_unique(indices, ["index", "date"], "bcb indices")
    config.INDICES_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    indices.write_parquet(config.INDICES_PARQUET, compression="zstd")
    return indices
