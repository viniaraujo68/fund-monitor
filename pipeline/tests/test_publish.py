import json
import math
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from fund_monitor import config
from fund_monitor.publish import site_json
from fund_monitor.publish.names import display_name, is_structural_vehicle, unique_display_names


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


def window_frame(has_history: bool) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "window": ["12m"],
            "base_date": [date(2025, 9, 22)],
            "end_date": [date(2026, 9, 22)],
            "business_days": [251],
            "has_history": [has_history],
            "fund_return": [0.14 if has_history else None],
            "fund_annualized": [0.1405 if has_history else None],
            "cdi_return": [0.145],
            "cdi_annualized": [0.1456],
            "pct_cdi": [0.9655 if has_history else None],
            "ima_b_return": [0.13],
            "ibov_return": [0.2],
        }
    )


def test_windows_keep_only_relevant_benchmarks() -> None:
    (row,) = site_json.build_windows(window_frame(True), ["cdi", "ima_b"])
    assert row.benchmark_returns == {"ima_b": 0.13}
    assert row.pct_cdi == 0.9655


def test_windows_without_history_hide_the_comparison() -> None:
    (row,) = site_json.build_windows(window_frame(False), ["cdi"])
    assert row.base_date is None
    assert row.cdi_return is None
    assert row.fund_return is None


def test_di_series_compare_only_with_cdi() -> None:
    assert site_json.series_benchmarks("Renda Fixa", "DI de um dia") == (["cdi"], None)
    assert site_json.series_benchmarks("Renda Fixa", "Índice de Mercado Andima NTN-B mais de 5 anos") == (["cdi", "ima_b"], "ima_b")
    assert site_json.series_benchmarks("Ações", "IBrX") == (["cdi", "ibov"], "ibov")
    assert site_json.series_benchmarks("Multimercado", "DI de um dia") == (["cdi"], None)


def test_no_peer_position_without_peers() -> None:
    assert site_json.build_peer_position({"peer_count": 0}, {}) is None
    assert site_json.build_peer_position(None, {}) is None


SITE = config.SITE_DIR


@pytest.mark.skipif(not (SITE / "meta.json").exists(), reason="site not published")
def test_published_site_matches_contract() -> None:
    meta = site_json.Meta.model_validate_json((SITE / "meta.json").read_text())
    funds = [site_json.FundSummary.model_validate(item) for item in json.loads((SITE / "funds.json").read_text())]
    site_json.Aggregates.model_validate_json((SITE / "aggregates.json").read_text())
    quality = site_json.QualityDocument.model_validate_json((SITE / "quality.json").read_text())
    details = sorted(Path(SITE / "funds").glob("*.json"))
    assert meta.universe.monitored_series == len(funds) == len(details)
    assert sum(quality.summary.by_severity.values()) == len(quality.issues)
    for path in details:
        detail = site_json.FundDetail.model_validate_json(path.read_text())
        assert detail.summary.series_id == path.stem
        assert all(len(values) == len(detail.cumulative.dates) for values in detail.cumulative.values.values())
