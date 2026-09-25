import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from fund_monitor import config
from fund_monitor.collect import anbima_ima, b3_ibovespa, bcb_sgs

FIXTURES = Path(__file__).parent / "fixtures"


def test_bcb_parse_keeps_rate_as_decimal() -> None:
    cdi = next(series for series in bcb_sgs.SERIES if series.name == "cdi")
    frame = bcb_sgs.parse_series(cdi, [{"data": "02/09/2024", "valor": "0.039270"}])
    assert frame.row(0) == ("cdi", date(2024, 9, 2), Decimal("0.03927"), "percent_per_day")


def test_anbima_parses_selected_indices() -> None:
    frame = anbima_ima.parse_ima_csv((FIXTURES / "anbima_ima_20260922.csv").read_bytes())
    assert sorted(frame["index"]) == sorted(config.ANBIMA_INDICES)
    ima_b = frame.filter(pl.col("index") == "IMA-B").row(0, named=True)
    assert ima_b == {
        "index": "IMA-B",
        "date": date(2026, 9, 22),
        "value": Decimal("11928.903982"),
        "daily_change_pct": Decimal("0.1093"),
    }


def test_anbima_empty_response_yields_no_rows() -> None:
    frame = anbima_ima.parse_ima_csv((FIXTURES / "anbima_ima_empty.csv").read_bytes())
    assert frame.is_empty()
    assert frame.schema == pl.Schema(anbima_ima.SCHEMA)


def test_anbima_weekdays_skip_weekend() -> None:
    assert anbima_ima.weekdays_between(date(2026, 9, 18), date(2026, 9, 21)) == [date(2026, 9, 18), date(2026, 9, 21)]


def test_anbima_retries_only_recent_empty_days(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ANBIMA_RAW_DIR", tmp_path)
    empty = (FIXTURES / "anbima_ima_empty.csv").read_bytes()
    anbima_ima.raw_path(date(2026, 9, 21)).write_bytes(empty)
    anbima_ima.raw_path(date(2026, 6, 1)).write_bytes(empty)
    anbima_ima.raw_path(date(2026, 9, 22)).write_bytes((FIXTURES / "anbima_ima_20260922.csv").read_bytes())
    reference = date(2026, 9, 24)
    assert anbima_ima.needs_fetch(date(2026, 9, 21), reference)
    assert not anbima_ima.needs_fetch(date(2026, 6, 1), reference)
    assert not anbima_ima.needs_fetch(date(2026, 9, 22), reference)
    assert anbima_ima.needs_fetch(date(2026, 9, 23), reference)


def test_b3_payload_is_base64_json() -> None:
    assert b3_ibovespa.request_payload(2026) == "eyJpbmRleCI6IklCT1YiLCJsYW5ndWFnZSI6InB0LWJyIiwieWVhciI6IjIwMjYifQ=="


def test_b3_parse_reads_day_by_month_matrix() -> None:
    document = json.loads((FIXTURES / "b3_ibov_2026_sample.json").read_text())
    frame = b3_ibovespa.parse_year(document, 2026)
    closes = dict(frame.select("date", "value").iter_rows())
    assert closes[date(2026, 1, 2)] == Decimal("160538.69")
    assert closes[date(2026, 8, 31)] == Decimal("177418.78")
    assert date(2026, 5, 1) not in closes
    assert frame.height == 19
