from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from fund_monitor import config
from fund_monitor.calc.benchmarks import benchmark_levels


def business_days(start: date, count: int) -> list[date]:
    days = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def quotas_frame(series_id: str, days: list[date], quotas: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "series_id": [series_id] * len(days),
            "cnpj": [series_id] * len(days),
            "subclass_id": [None] * len(days),
            "date": days,
            "quota_value": [Decimal(f"{quota:.12f}") for quota in quotas],
            "inherited": [False] * len(days),
        },
        schema_overrides={"quota_value": pl.Decimal(28, 12), "subclass_id": pl.String},
    )


def levels_frame(days: list[date], cdi_percent: float, ima_b: list[float] | None = None) -> pl.DataFrame:
    indices = pl.DataFrame(
        {"index": "cdi", "date": days, "value": [Decimal(str(cdi_percent))] * len(days), "unit": "percent_per_day"},
        schema_overrides={"value": pl.Decimal(18, 8)},
    )
    ima = pl.DataFrame(
        {"index": "IMA-B", "date": days if ima_b else [], "value": ima_b or []},
        schema={"index": pl.String, "date": pl.Date, "value": pl.Float64},
    )
    ibovespa = pl.DataFrame(schema={"index": pl.String, "date": pl.Date, "value": pl.Float64})
    return benchmark_levels(indices, ima, ibovespa, ibovespa)


def compound(start: float, returns: list[float]) -> list[float]:
    values = [start]
    for daily_return in returns:
        values.append(values[-1] * (1 + daily_return))
    return values


MANAGER = "00000000000100"
DAILY_SCHEMA = {
    "cnpj": pl.String,
    "subclass_id": pl.String,
    "date": pl.Date,
    "report_type": pl.String,
    "quota_value": pl.Decimal(28, 12),
    "net_assets": pl.Decimal(20, 2),
    "total_assets": pl.Decimal(20, 2),
    "inflows": pl.Decimal(20, 2),
    "outflows": pl.Decimal(20, 2),
    "shareholders": pl.Int64,
}
REGISTRY_SCHEMA = {
    "cnpj": pl.String,
    "subclass_id": pl.String,
    "class_registry_id": pl.String,
    "fund_registry_id": pl.String,
    "fund_cnpj": pl.String,
    "fund_name": pl.String,
    "class_name": pl.String,
    "subclass_name": pl.String,
    "fund_status": pl.String,
    "class_status": pl.String,
    "subclass_status": pl.String,
    "class_start_date": pl.Date,
    "subclass_start_date": pl.Date,
    "class_type": pl.String,
    "cvm_classification": pl.String,
    "anbima_classification": pl.String,
    "performance_benchmark": pl.String,
    "condominium": pl.String,
    "exclusive": pl.Boolean,
    "target_audience": pl.String,
    "long_term_taxation": pl.Boolean,
    "class_net_assets": pl.Decimal(20, 2),
    "class_net_assets_date": pl.Date,
    "administrator_name": pl.String,
    "manager_cnpjs": pl.List(pl.String),
    "manager_names": pl.List(pl.String),
    "subclass_reported": pl.Boolean,
}


def registry_row(cnpj: str, class_name: str, manager: str = MANAGER, **overrides: object) -> dict:
    row = {
        "cnpj": cnpj,
        "subclass_id": None,
        "class_registry_id": f"R{cnpj}",
        "fund_registry_id": f"F{cnpj}",
        "fund_cnpj": cnpj,
        "fund_name": class_name,
        "class_name": class_name,
        "subclass_name": None,
        "fund_status": "Em Funcionamento Normal",
        "class_status": "Em Funcionamento Normal",
        "subclass_status": None,
        "class_start_date": date(2020, 1, 1),
        "subclass_start_date": None,
        "class_type": "Classes de Cotas de Fundos FIF",
        "cvm_classification": "Renda Fixa",
        "anbima_classification": "Renda Fixa Duração Baixa Grau de Investimento",
        "performance_benchmark": "DI de um dia",
        "condominium": "Aberto",
        "exclusive": False,
        "target_audience": "Público Geral",
        "long_term_taxation": False,
        "class_net_assets": None,
        "class_net_assets_date": None,
        "administrator_name": "ADMIN",
        "manager_cnpjs": [manager],
        "manager_names": ["GESTORA TESTE"],
        "subclass_reported": False,
    }
    return {**row, **overrides}


def registry_frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=REGISTRY_SCHEMA)


def daily_frame(cnpj: str, days: list[date], quotas: list[float], net_assets: float, **overrides: object) -> pl.DataFrame:
    rows = [
        {
            "cnpj": cnpj,
            "subclass_id": None,
            "date": day,
            "report_type": "CLASSES - FIF",
            "quota_value": Decimal(f"{quota:.12f}"),
            "net_assets": Decimal(f"{net_assets:.2f}"),
            "total_assets": Decimal(f"{net_assets:.2f}"),
            "inflows": Decimal("0"),
            "outflows": Decimal("0"),
            "shareholders": 10,
            **overrides,
        }
        for day, quota in zip(days, quotas)
    ]
    return pl.DataFrame(rows, schema=DAILY_SCHEMA)


def install_sources(root: Path, monkeypatch: pytest.MonkeyPatch, daily: pl.DataFrame, peer_daily: pl.DataFrame, days: list[date]) -> None:
    paths = {
        "DAILY_PARQUET_DIR": root / "daily",
        "PEER_DAILY_PARQUET_DIR": root / "peers_daily",
        "INDICES_PARQUET": root / "indices.parquet",
        "IMA_PARQUET": root / "ima.parquet",
        "IBOVESPA_PARQUET": root / "ibovespa.parquet",
        "IBRX_PARQUET": root / "ibrx100.parquet",
        "METRICS_DIR": root / "metrics",
        "SITE_DIR": root / "site",
        "TRIAGE_FILE": root / "triage.json",
    }
    for name, path in paths.items():
        monkeypatch.setattr(config, name, path)
    monkeypatch.setattr(config, "MANAGER_CNPJ", MANAGER)
    paths["DAILY_PARQUET_DIR"].mkdir()
    paths["PEER_DAILY_PARQUET_DIR"].mkdir()
    daily.write_parquet(paths["DAILY_PARQUET_DIR"] / "daily.parquet")
    peer_daily.select(config.PEER_DAILY_COLUMNS).write_parquet(paths["PEER_DAILY_PARQUET_DIR"] / "peers.parquet")
    pl.DataFrame(
        {"index": "cdi", "date": days, "value": [Decimal("0.05")] * len(days), "unit": "percent_per_day"},
        schema_overrides={"value": pl.Decimal(18, 8)},
    ).write_parquet(paths["INDICES_PARQUET"])
    pl.DataFrame({"index": "IMA-B", "date": days, "value": [1000.0 + p for p in range(len(days))]}).write_parquet(paths["IMA_PARQUET"])
    pl.DataFrame({"index": "IBOV", "date": days, "value": [100000.0 + 10 * p for p in range(len(days))]}).write_parquet(paths["IBOVESPA_PARQUET"])
    pl.DataFrame({"index": "IBXX", "date": days, "value": [40000.0 + 4 * p for p in range(len(days))]}).write_parquet(paths["IBRX_PARQUET"])


SAMPLE_DAYS = business_days(date(2025, 1, 2), 300)
SAMPLE_ZEROED_DAY = date(2026, 1, 30)
SAMPLE_PARTIAL_DAY = date(2026, 2, 26)
SAMPLE_PEER_RATES = {f"P{n}": 0.0003 + 0.0001 * n for n in range(1, 6)}


def wavy(rate: float, count: int = 300) -> list[float]:
    return compound(1.0, ([rate + 0.0001, rate - 0.0001] * count)[: count - 1])


def zeroed_on(frame: pl.DataFrame, day: date) -> pl.DataFrame:
    zeros = {"quota_value": Decimal("0"), "net_assets": Decimal("0"), "shareholders": 0}
    return frame.with_columns(
        pl.when(pl.col("date") == day).then(pl.lit(value, dtype=DAILY_SCHEMA[column])).otherwise(pl.col(column)).alias(column)
        for column, value in zeros.items()
    )


def sample_sources() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    fund_a = zeroed_on(daily_frame("A", SAMPLE_DAYS, wavy(0.00055), 200_000_000), SAMPLE_ZEROED_DAY)
    fund_b = daily_frame("B", [*SAMPLE_DAYS, SAMPLE_PARTIAL_DAY], wavy(0.0005, 301), 100_000_000)
    peers = [daily_frame(cnpj, SAMPLE_DAYS, wavy(rate), 100_000_000) for cnpj, rate in SAMPLE_PEER_RATES.items()]
    registry = registry_frame(
        [
            registry_row("A", "ICATU VANGUARDA ALFA FIF - CLASSE DE INVESTIMENTO RENDA FIXA"),
            registry_row("B", "ICATU VANGUARDA BETA FIF - CLASSE DE INVESTIMENTO RENDA FIXA"),
            *(registry_row(cnpj, f"OUTRO {cnpj} FIF", manager="99999999000199") for cnpj in SAMPLE_PEER_RATES),
        ]
    )
    return pl.concat([fund_a, fund_b]), pl.concat([fund_a, fund_b, *peers]), registry
