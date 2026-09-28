import json
import math
import shutil
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from builders import SAMPLE_DAYS, business_days, compound, install_sources, levels_frame, quotas_frame, sample_sources
from fund_monitor import config
from fund_monitor.calc.engine import calculate, write_metrics
from fund_monitor.calc.peers import MIN_PEERS
from fund_monitor.calc.returns import window_returns
from fund_monitor.publish import site_json
from fund_monitor.publish.names import display_name, is_structural_vehicle, unique_display_names
from fund_monitor.quality.checks import ISSUE_SCHEMA
from fund_monitor.quality.report import run_quality


def test_rounded_drops_non_finite_and_negative_zero() -> None:
    assert site_json.rounded(None, 4) is None
    assert site_json.rounded(math.inf, 4) is None
    assert site_json.rounded(math.nan, 4) is None
    assert math.copysign(1, site_json.rounded(-0.00000001, 4)) == 1
    assert site_json.rounded(0.1234567, 4) == 0.1235


def test_display_name_strips_manager_and_legal_suffix() -> None:
    assert display_name("ICATU VANGUARDA SIMPLES SOBERANO FIF - CLASSE DE INVESTIMENTO RENDA FIXA - RESP LIMITADA", None) == "Simples Soberano"
    assert display_name("ICATU VANGUARDA DIVIDENDOS FIF - CLASSE", "ICATU VANGUARDA DIVIDENDOS SUBCLASSE DE INVESTIMENTO EM AÇÕES") == "Dividendos"
    assert display_name("ICATU VANGUARDA IU 95/5 FIF - CIC MULTIMERCADO", None) == "IU 95/5"


def test_duplicate_names_get_a_qualifier() -> None:
    names = unique_display_names(
        [
            ("ICATU VANGUARDA IBX FIF - CLASSE DE INVESTIMENTO EM AÇÕES", None),
            ("ICATU VANGUARDA IBX FIFE FIF  CLASSE DE INVESTIMENTO EM AÇÕES PREVIDENCIÁRIO", None),
            ("ICATU VANGUARDA INFLAÇÃO CURTA FIF - CLASSE DE INVESTIMENTO EM COTAS RENDA FIXA LP", None),
            ("ICATU VANGUARDA INFLAÇÃO CURTA FIF - CLASSE DE INVESTIMENTO RENDA FIXA LONGO PRAZO", None),
        ]
    )
    assert names == ["IBX", "IBX FIFE", "Inflação Curta FIC", "Inflação Curta"]


def test_structural_vehicle_markers() -> None:
    assert is_structural_vehicle("ICATU VANGUARDA VEÍCULO ESPECIAL BANCÁRIO  FIF - CLASSE")
    assert is_structural_vehicle("ICATU VANGUARDA ABSOLUTO FIFE FIF - CLASSE")
    assert not is_structural_vehicle("ICATU VANGUARDA ABSOLUTO FIF - CLASSE")


def twelve_month_windows(count: int) -> pl.DataFrame:
    days = business_days(date(2025, 1, 2), 300)
    quotas = quotas_frame("A", days[-count:], compound(1.0, [0.0006] * (count - 1)))
    ima_b = [1000.0 + position for position in range(300)]
    return window_returns(quotas, levels_frame(days, 0.05, ima_b=ima_b), as_of=days[-1]).filter(pl.col("window") == "12m")


def test_windows_keep_only_relevant_benchmarks() -> None:
    (row,) = site_json.build_windows(twelve_month_windows(300), ["cdi", "ima_b"])
    assert set(row.benchmark_returns) == {"ima_b"}
    assert row.benchmark_returns["ima_b"] is not None
    assert row.pct_cdi is not None
    assert row.cdi_annualized is not None


def test_windows_without_history_hide_the_comparison() -> None:
    (row,) = site_json.build_windows(twelve_month_windows(100), ["cdi", "ima_b"])
    assert (row.base_date, row.business_days, row.fund_return, row.fund_annualized) == (None, None, None, None)
    assert (row.cdi_return, row.cdi_annualized, row.pct_cdi) == (None, None, None)
    assert row.benchmark_returns == {"ima_b": None}


def test_di_series_compare_only_with_cdi() -> None:
    assert site_json.series_benchmarks("Renda Fixa", "DI de um dia") == (["cdi"], None)
    assert site_json.series_benchmarks("Renda Fixa", "Índice de Mercado Andima NTN-B mais de 5 anos") == (["cdi", "ima_b"], "ima_b")
    assert site_json.series_benchmarks("Ações", "IBrX") == (["cdi", "ibov"], "ibov")
    assert site_json.series_benchmarks("Multimercado", "DI de um dia") == (["cdi"], None)


def test_no_peer_position_without_peers() -> None:
    assert site_json.build_peer_position({"peer_count": 0}) is None
    assert site_json.build_peer_position(None) is None


def peer_position(peer_count: int) -> dict:
    measured = {f"{metric}_{label}": 0.1 for metric in ("fund_return", "volatility", "max_drawdown") for label in ("percentile", "p25", "median", "p75")}
    values = {"fund_return": 0.12, "volatility": 0.01, "max_drawdown": -0.02}
    return {"anbima_classification": "RF", "target_audience": "Público Geral", "peer_count": peer_count, **values, **measured}


def test_peer_position_needs_the_minimum_number_of_peers() -> None:
    assert site_json.build_peer_position(peer_position(MIN_PEERS - 1)) is None
    position = site_json.build_peer_position(peer_position(MIN_PEERS))
    assert position is not None
    assert position.metrics["fund_return"].value == 0.12
    assert set(position.metrics) == {"fund_return", "volatility", "max_drawdown"}


def fund_attribute() -> dict:
    return {
        "series_id": "A-S1",
        "cnpj": "A",
        "subclass_id": "S1",
        "display_name": "Alfa",
        "class_name": "ALFA FIF",
        "subclass_name": "ALFA SUBCLASSE",
        "cvm_classification": "Renda Fixa",
        "anbima_classification": "RF",
        "target_audience": "Público Geral",
        "condominium": "Aberto",
        "performance_benchmark": "DI de um dia",
        "structural_vehicle": False,
    }


def test_inherited_until_comes_from_the_whole_series() -> None:
    days = business_days(date(2024, 9, 2), 600)
    quotas = quotas_frame("A-S1", days, compound(1.0, [0.0005] * 599)).with_columns(inherited=pl.col("date") <= days[10])
    windows = window_returns(quotas, levels_frame(days, 0.05), as_of=days[-1])
    risk = pl.DataFrame(schema={"window": pl.String, "volatility": pl.Float64, "max_drawdown": pl.Float64, "sharpe": pl.Float64})
    summary = site_json.build_summary(fund_attribute(), windows, risk, None, None, pl.DataFrame(schema=ISSUE_SCHEMA))
    assert summary.inherited_until == days[10]
    assert summary.first_date == days[0]


def test_monthly_residual_keeps_the_precision_of_the_rule() -> None:
    flows = pl.DataFrame(
        {
            "month": [date(2026, 3, 1)],
            "net_flow": [0.0],
            "inflows": [0.0],
            "outflows": [0.0],
            "net_assets_end": [100.0],
            "shareholders_end": [1],
            "monthly_return": [0.01],
            "unexplained_share": [0.0100312],
        }
    )
    (row,) = site_json.build_flows(flows)
    assert row.unexplained_share == 0.010031
    assert row.unexplained_share > 0.01


def test_sibling_subclasses_with_the_same_short_name_stay_distinct() -> None:
    names = unique_display_names(
        [
            ("ICATU VANGUARDA X FIF - CLASSE", "ICATU VANGUARDA X SUBCLASSE I"),
            ("ICATU VANGUARDA X FIF - CLASSE", "ICATU VANGUARDA X SUBCLASSE II"),
            ("ICATU VANGUARDA X FIF - CLASSE", "ICATU VANGUARDA X SUBCLASSE III"),
        ]
    )
    assert names == ["X", "X 2", "X 3"]


def test_short_function_words_are_lowercase() -> None:
    assert display_name("ICATU VANGUARDA CRÉDITO PRIVADO DOS TRABALHADORES FIF", None) == "Crédito Privado dos Trabalhadores"
    assert display_name("ICATU VANGUARDA RENDA PARA APOSENTADORIA COM PROTEÇÃO SEM LIMITE FIF", None) == "Renda para Aposentadoria com Proteção sem Limite"
    assert display_name("ICATU VANGUARDA RETORNO ÀS METAS POR PRAZO AO INVESTIDOR À VISTA FIF", None) == "Retorno às Metas por Prazo ao Investidor à Vista"


@pytest.fixture(scope="module")
def published_site(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    daily, peer_daily, registry = sample_sources()
    with pytest.MonkeyPatch.context() as monkeypatch:
        install_sources(tmp_path_factory.mktemp("site"), monkeypatch, daily, peer_daily, SAMPLE_DAYS)
        write_metrics(calculate(registry))
        run_quality(registry, date(2026, 2, 27))
        site_json.publish_site(registry, date(2026, 2, 27))
        yield config.SITE_DIR


def test_published_site_matches_contract(published_site: Path) -> None:
    meta = site_json.Meta.model_validate_json((published_site / "meta.json").read_text())
    funds = json.loads((published_site / "funds.json").read_text())
    assert meta.as_of == SAMPLE_DAYS[-1]
    assert meta.universe.monitored_series == len(funds) == 2
    detail = site_json.FundDetail.model_validate_json((published_site / site_json.FUNDS_DIRECTORY / "A.json").read_text())
    assert detail.peers is not None
    assert detail.peers.peer_count == 6
    assert detail.summary.issues.high == 1


def test_publish_fails_when_the_written_site_breaks_the_contract(published_site: Path, tmp_path: Path) -> None:
    site = shutil.copytree(published_site, tmp_path / "site")
    (site / site_json.FUNDS_DIRECTORY / "B.json").unlink()
    with pytest.raises(ValueError, match="fund files"):
        site_json.verify_site(site)
    meta = json.loads((site / "meta.json").read_text())
    (site / "meta.json").write_text(json.dumps({**meta, "unexpected": 1}))
    with pytest.raises(ValueError, match="unexpected"):
        site_json.verify_site(site)
