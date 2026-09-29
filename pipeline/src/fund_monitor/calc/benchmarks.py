from datetime import timedelta

import polars as pl

from fund_monitor import config

CDI = "cdi"
IMA_B = "ima_b"
IBOVESPA = "ibov"
IBRX = "ibrx"
LEVEL_TOLERANCE = "7d"

BENCHMARKS_BY_CLASSIFICATION = {
    "Renda Fixa": (CDI, IMA_B),
    "Multimercado": (CDI,),
    "Ações": (CDI, IBOVESPA),
}
MARKET_BENCHMARK_BY_CLASSIFICATION = {"Renda Fixa": IMA_B, "Ações": IBOVESPA}


def cdi_levels(indices: pl.DataFrame) -> pl.DataFrame:
    cdi = indices.filter(pl.col("index") == CDI).sort("date")
    accrued = cdi.select(
        (pl.col("date") + timedelta(days=1)).alias("date"),
        (1 + pl.col("value").cast(pl.Float64) / 100).cum_prod().alias("level"),
        pl.int_range(1, pl.len() + 1).alias("accruals"),
    )
    start = pl.DataFrame(
        {"date": [cdi["date"].min()], "level": [1.0], "accruals": [0]},
        schema=accrued.schema,
    )
    return pl.concat([start, accrued]).with_columns(benchmark=pl.lit(CDI))


def index_levels(frame: pl.DataFrame, benchmark: str) -> pl.DataFrame:
    return frame.sort("date").select(
        "date",
        pl.col("value").cast(pl.Float64).alias("level"),
        pl.lit(None, dtype=pl.Int64).alias("accruals"),
        pl.lit(benchmark).alias("benchmark"),
    )


def benchmark_levels(indices: pl.DataFrame, ima: pl.DataFrame, ibovespa: pl.DataFrame, ibrx: pl.DataFrame) -> pl.DataFrame:
    return pl.concat(
        [
            cdi_levels(indices),
            index_levels(ima.filter(pl.col("index") == "IMA-B"), IMA_B),
            index_levels(ibovespa, IBOVESPA),
            index_levels(ibrx, IBRX),
        ]
    )


def read_benchmark_levels() -> pl.DataFrame:
    return benchmark_levels(
        pl.read_parquet(config.INDICES_PARQUET),
        pl.read_parquet(config.IMA_PARQUET),
        pl.read_parquet(config.IBOVESPA_PARQUET),
        pl.read_parquet(config.IBRX_PARQUET),
    )


def attach_level(
    frame: pl.DataFrame, levels: pl.DataFrame, benchmark: str, date_column: str, alias: str, value: str = "level"
) -> pl.DataFrame:
    right = (
        levels.filter(pl.col("benchmark") == benchmark)
        .select(pl.col("date").alias("level_date"), pl.col(value).alias(alias))
        .sort("level_date")
    )
    return (
        frame.sort(date_column)
        .join_asof(right, left_on=date_column, right_on="level_date", strategy="backward", tolerance=LEVEL_TOLERANCE)
        .drop("level_date")
    )


def attach_accruals(frame: pl.DataFrame, levels: pl.DataFrame, date_column: str, alias: str) -> pl.DataFrame:
    return attach_level(frame, levels, CDI, date_column, alias, "accruals")
