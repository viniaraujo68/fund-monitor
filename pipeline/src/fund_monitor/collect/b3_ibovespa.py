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


def request_payload(year: int) -> str:
    query = json.dumps({"index": config.B3_INDEX, "language": "pt-br", "year": str(year)}, separators=(",", ":"))
    return base64.b64encode(query.encode()).decode()


def raw_path(year: int) -> Path:
    return config.B3_RAW_DIR / f"{config.B3_INDEX.lower()}_{year}.json"


def parse_year(document: dict, year: int) -> pl.DataFrame:
    closes = [
        (date(year, month, entry["day"]), entry[f"rateValue{month}"])
        for entry in document["results"]
        for month in range(1, 13)
        if entry.get(f"rateValue{month}")
    ]
    frame = pl.DataFrame(closes, schema={"date": pl.Date, "close": pl.String}, orient="row")
    return frame.select(
        pl.lit(config.B3_INDEX).alias("index"),
        "date",
        parse_brazilian_number("close").cast(INDEX_LEVEL, strict=True).alias("value"),
    )


def last_expected_session(year: int) -> date:
    day = date(year, 12, 30)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def is_final(year: int) -> bool:
    path = raw_path(year)
    year_end = date(year, 12, 31)
    written = date.fromtimestamp(path.stat().st_mtime)
    if written <= year_end:
        return False
    if written > year_end + timedelta(days=REFRESH_GRACE_DAYS):
        return True
    closes = parse_year(json.loads(path.read_bytes()), year)
    return closes.height > 0 and closes["date"].max() >= last_expected_session(year)


def needs_fetch(year: int, reference_date: date) -> bool:
    return year >= reference_date.year or not raw_path(year).exists() or not is_final(year)


def fetch_year(client: httpx.Client, year: int, reference_date: date) -> None:
    response = client.get(config.B3_INDEX_URL.format(payload=request_payload(year)))
    response.raise_for_status()
    try:
        closes = parse_year(json.loads(response.content), year)
    except (ValueError, KeyError, TypeError, pl.exceptions.PolarsError) as error:
        raise ValueError(f"b3 {year}: unreadable reply, not saved: {response.content[:80]!r}") from error
    if year < reference_date.year and closes.is_empty():
        raise ValueError(f"b3 {year}: reply for a past year has no closes, not saved")
    raw_path(year).parent.mkdir(parents=True, exist_ok=True)
    raw_path(year).write_bytes(response.content)


def collect_ibovespa(start: date, reference_date: date) -> pl.DataFrame:
    years = range(start.year, reference_date.year + 1)
    with httpx.Client(timeout=60.0) as client:
        for year in years:
            if needs_fetch(year, reference_date):
                fetch_year(client, year, reference_date)
    frames = [parse_year(json.loads(raw_path(year).read_bytes()), year) for year in years]
    ibovespa = (
        pl.concat(frames).filter(pl.col("date") >= start, pl.col("date") < reference_date).sort("date")
    )
    ensure_unique(ibovespa, ["date"], "b3 ibovespa")
    config.IBOVESPA_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    ibovespa.write_parquet(config.IBOVESPA_PARQUET, compression="zstd")
    logger.info("b3 %s: %d closes, last %s", config.B3_INDEX, ibovespa.height, ibovespa["date"].max())
    return ibovespa
