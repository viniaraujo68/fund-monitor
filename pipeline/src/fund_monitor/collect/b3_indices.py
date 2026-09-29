import base64
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import httpx
import polars as pl

from fund_monitor import config
from fund_monitor.collect.numbers import INDEX_LEVEL, parse_brazilian_number
from fund_monitor.validation import ensure_unique

logger = logging.getLogger(__name__)

REFRESH_GRACE_DAYS = 10


def parquet_path(index: str) -> Path:
    return {config.B3_IBOVESPA: config.IBOVESPA_PARQUET, config.B3_IBRX: config.IBRX_PARQUET}[index]


def request_payload(year: int, index: str = config.B3_IBOVESPA) -> str:
    query = json.dumps({"index": index, "language": "pt-br", "year": str(year)}, separators=(",", ":"))
    return base64.b64encode(query.encode()).decode()


def raw_path(year: int, index: str = config.B3_IBOVESPA) -> Path:
    return config.B3_RAW_DIR / f"{index.lower()}_{year}.json"


def parse_year(document: dict, year: int, index: str = config.B3_IBOVESPA) -> pl.DataFrame:
    closes = [
        (date(year, month, entry["day"]), entry[f"rateValue{month}"])
        for entry in document["results"]
        for month in range(1, 13)
        if entry.get(f"rateValue{month}")
    ]
    frame = pl.DataFrame(closes, schema={"date": pl.Date, "close": pl.String}, orient="row")
    return frame.select(
        pl.lit(index).alias("index"),
        "date",
        parse_brazilian_number("close").cast(INDEX_LEVEL, strict=True).alias("value"),
    )


def last_expected_session(year: int) -> date:
    day = date(year, 12, 30)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def is_final(year: int, index: str = config.B3_IBOVESPA) -> bool:
    path = raw_path(year, index)
    year_end = date(year, 12, 31)
    written = date.fromtimestamp(path.stat().st_mtime)
    if written <= year_end:
        return False
    if written > year_end + timedelta(days=REFRESH_GRACE_DAYS):
        return True
    closes = parse_year(json.loads(path.read_bytes()), year, index)
    return closes.height > 0 and closes["date"].max() >= last_expected_session(year)


def needs_fetch(year: int, reference_date: date, index: str = config.B3_IBOVESPA) -> bool:
    return year >= reference_date.year or not raw_path(year, index).exists() or not is_final(year, index)


def fetch_year(client: httpx.Client, year: int, reference_date: date, index: str = config.B3_IBOVESPA) -> None:
    response = client.get(config.B3_INDEX_URL.format(payload=request_payload(year, index)))
    response.raise_for_status()
    try:
        closes = parse_year(json.loads(response.content), year, index)
    except (ValueError, KeyError, TypeError, pl.exceptions.PolarsError) as error:
        raise ValueError(f"b3 {index} {year}: unreadable reply, not saved: {response.content[:80]!r}") from error
    if year < reference_date.year and closes.is_empty():
        raise ValueError(f"b3 {index} {year}: reply for a past year has no closes, not saved")
    raw_path(year, index).parent.mkdir(parents=True, exist_ok=True)
    raw_path(year, index).write_bytes(response.content)


def collect_index(start: date, reference_date: date, index: str = config.B3_IBOVESPA) -> pl.DataFrame:
    years = range(start.year, reference_date.year + 1)
    with httpx.Client(timeout=60.0) as client:
        for year in years:
            if needs_fetch(year, reference_date, index):
                fetch_year(client, year, reference_date, index)
    frames = [parse_year(json.loads(raw_path(year, index).read_bytes()), year, index) for year in years]
    closes = pl.concat(frames).filter(pl.col("date") >= start, pl.col("date") < reference_date).sort("date")
    ensure_unique(closes, ["date"], f"b3 {index}")
    path = parquet_path(index)
    path.parent.mkdir(parents=True, exist_ok=True)
    closes.write_parquet(path, compression="zstd")
    logger.info("b3 %s: %d closes, last %s", index, closes.height, closes["date"].max())
    return closes


def collect_b3_indices(start: date, reference_date: date) -> None:
    for index in config.B3_INDICES:
        collect_index(start, reference_date, index)
