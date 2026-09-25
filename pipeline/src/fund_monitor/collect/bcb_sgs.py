import json
import logging
from dataclasses import dataclass
from datetime import date

import httpx
import polars as pl

from fund_monitor import config
from fund_monitor.collect.numbers import RATE
from fund_monitor.validation import ensure_unique

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SgsSeries:
    name: str
    series_id: int
    unit: str


SERIES = (
    SgsSeries("cdi", 12, "percent_per_day"),
    SgsSeries("selic", 11, "percent_per_day"),
    SgsSeries("ipca", 433, "percent_per_month"),
    SgsSeries("igpm", 189, "percent_per_month"),
)


def fetch_series(client: httpx.Client, series: SgsSeries, start: date, end: date) -> list[dict[str, str]]:
    response = client.get(
        config.BCB_SGS_URL.format(series_id=series.series_id),
        params={"formato": "json", "dataInicial": f"{start:%d/%m/%Y}", "dataFinal": f"{end:%d/%m/%Y}"},
    )
    response.raise_for_status()
    return response.json()


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
            records = fetch_series(client, series, start, end)
            (config.BCB_RAW_DIR / f"sgs_{series.series_id}.json").write_text(json.dumps(records))
            frame = parse_series(series, records)
            logger.info("bcb %s: %d values, last %s", series.name, frame.height, frame["date"].max())
            frames.append(frame)
    indices = pl.concat(frames).sort("index", "date")
    ensure_unique(indices, ["index", "date"], "bcb indices")
    config.INDICES_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    indices.write_parquet(config.INDICES_PARQUET, compression="zstd")
    return indices
