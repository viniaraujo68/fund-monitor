import base64
import json
import os
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import polars as pl
import pytest

from fund_monitor import config
from fund_monitor.collect import anbima_ima, b3_indices, bcb_sgs

FIXTURES = Path(__file__).parent / "fixtures"
UNEXPECTED_REPLY = b"<html><body>Servico temporariamente indisponivel</body></html>"


def mock_http(monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def b3_year(request: httpx.Request) -> int:
    payload = request.url.path.rsplit("/", 1)[-1]
    return int(json.loads(base64.b64decode(payload))["year"])


def b3_document(closes: dict[date, str]) -> bytes:
    results = [{"day": day.day, f"rateValue{day.month}": close} for day, close in closes.items()]
    return json.dumps({"results": results}).encode()


def write_with_mtime(path: Path, content: bytes, written: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (written.timestamp(), written.timestamp()))


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
    assert b3_indices.request_payload(2026) == "eyJpbmRleCI6IklCT1YiLCJsYW5ndWFnZSI6InB0LWJyIiwieWVhciI6IjIwMjYifQ=="


def test_b3_parse_reads_day_by_month_matrix() -> None:
    document = json.loads((FIXTURES / "b3_ibov_2026_sample.json").read_text())
    frame = b3_indices.parse_year(document, 2026)
    closes = dict(frame.select("date", "value").iter_rows())
    assert closes[date(2026, 1, 2)] == Decimal("160538.69")
    assert closes[date(2026, 8, 31)] == Decimal("177418.78")
    assert date(2026, 5, 1) not in closes
    assert frame.height == 19


def test_bcb_collects_only_the_cdi_and_keeps_the_reply_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "BCB_RAW_DIR", tmp_path / "bcb")
    monkeypatch.setattr(config, "INDICES_PARQUET", tmp_path / "indices.parquet")
    reply = b'[{"data":"02/09/2024","valor":"0.039270"},\n {"data":"03/09/2024","valor":"0.039270"}]'
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, content=reply)

    mock_http(monkeypatch, handler)
    indices = bcb_sgs.collect_bcb(date(2024, 9, 1), date(2024, 9, 3))
    assert requested == ["/dados/serie/bcdata.sgs.12/dados"]
    assert (tmp_path / "bcb" / "sgs_12.json").read_bytes() == reply
    assert indices["index"].unique().to_list() == ["cdi"]
    assert indices.height == 2


def test_anbima_rejects_an_unexpected_reply() -> None:
    with pytest.raises(ValueError, match="unexpected anbima reply"):
        anbima_ima.parse_ima_csv(UNEXPECTED_REPLY)
    assert not anbima_ima.is_expected_reply(UNEXPECTED_REPLY)
    assert anbima_ima.is_expected_reply((FIXTURES / "anbima_ima_empty.csv").read_bytes())


def test_anbima_unexpected_reply_is_not_saved_and_is_fetched_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ANBIMA_RAW_DIR", tmp_path)
    old_day, reference = date(2026, 6, 1), date(2026, 9, 24)
    with mock_client(lambda request: httpx.Response(200, content=UNEXPECTED_REPLY)) as client:
        anbima_ima.fetch_day(client, old_day)
    assert not anbima_ima.raw_path(old_day).exists()
    assert anbima_ima.needs_fetch(old_day, reference)
    assert anbima_ima.read_day(old_day).is_empty()
    anbima_ima.raw_path(old_day).write_bytes(UNEXPECTED_REPLY)
    assert anbima_ima.needs_fetch(old_day, reference)
    with mock_client(lambda request: httpx.Response(200, content=(FIXTURES / "anbima_ima_empty.csv").read_bytes())) as client:
        anbima_ima.fetch_day(client, old_day)
    assert not anbima_ima.needs_fetch(old_day, reference)


def test_anbima_drops_rows_dated_otherwise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ANBIMA_RAW_DIR", tmp_path)
    content = (FIXTURES / "anbima_ima_20260922.csv").read_bytes()
    anbima_ima.raw_path(date(2026, 9, 22)).write_bytes(content)
    anbima_ima.raw_path(date(2026, 9, 23)).write_bytes(content)
    assert anbima_ima.read_day(date(2026, 9, 23)).is_empty()
    assert anbima_ima.read_day(date(2026, 9, 22)).height == len(config.ANBIMA_INDICES)


def test_b3_drops_the_reference_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "B3_RAW_DIR", tmp_path / "b3")
    monkeypatch.setattr(config, "IBOVESPA_PARQUET", tmp_path / "ibovespa.parquet")
    sample = (FIXTURES / "b3_ibov_2026_sample.json").read_bytes()
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=sample))
    closes = set(b3_indices.collect_index(date(2026, 1, 1), date(2026, 8, 31))["date"])
    assert date(2026, 8, 31) not in closes
    assert date(2026, 7, 31) in closes


@pytest.mark.parametrize(
    "reply", [b"<html>manutencao</html>", b'{"results": []}', b'{"results": [{"day": 2, "rateValue1": null}]}']
)
def test_b3_past_year_reply_is_checked_before_it_is_saved(
    reply: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "B3_RAW_DIR", tmp_path)
    with mock_client(lambda request: httpx.Response(200, content=reply)) as client:
        with pytest.raises(ValueError, match="b3 IBOV 2026"):
            b3_indices.fetch_year(client, 2026, date(2027, 1, 4))
    assert not b3_indices.raw_path(2026).exists()


def test_b3_current_year_may_have_no_close_yet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "B3_RAW_DIR", tmp_path)
    with mock_client(lambda request: httpx.Response(200, content=b'{"results": []}')) as client:
        b3_indices.fetch_year(client, 2027, date(2027, 1, 4))
    assert b3_indices.raw_path(2027).exists()


def test_b3_fetches_each_year_it_needs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "B3_RAW_DIR", tmp_path / "b3")
    monkeypatch.setattr(config, "IBOVESPA_PARQUET", tmp_path / "ibovespa.parquet")
    final_2025 = b3_document({date(2025, 12, 29): "160.000,00", date(2025, 12, 30): "161.000,00"})
    write_with_mtime(b3_indices.raw_path(2025), final_2025, datetime(2026, 1, 2, 20))
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(b3_year(request))
        return httpx.Response(200, content=b3_document({date(2026, 1, 2): "162.000,00"}))

    mock_http(monkeypatch, handler)
    ibovespa = b3_indices.collect_index(date(2025, 12, 1), date(2026, 1, 5))
    assert requested == [2026]
    assert ibovespa["date"].to_list() == [date(2025, 12, 29), date(2025, 12, 30), date(2026, 1, 2)]


def test_b3_collects_each_index_into_its_own_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "B3_RAW_DIR", tmp_path / "b3")
    monkeypatch.setattr(config, "IBOVESPA_PARQUET", tmp_path / "ibovespa.parquet")
    monkeypatch.setattr(config, "IBRX_PARQUET", tmp_path / "ibrx100.parquet")
    closes = {"IBOV": "162.000,00", "IBXX": "68.000,00"}

    def handler(request: httpx.Request) -> httpx.Response:
        index = json.loads(base64.b64decode(request.url.path.rsplit("/", 1)[-1]))["index"]
        return httpx.Response(200, content=b3_document({date(2026, 1, 2): closes[index]}))

    mock_http(monkeypatch, handler)
    b3_indices.collect_b3_indices(date(2026, 1, 1), date(2026, 1, 5))
    ibrx = pl.read_parquet(tmp_path / "ibrx100.parquet")
    assert ibrx.select("index", "value").rows() == [("IBXX", 68000.0)]
    assert pl.read_parquet(tmp_path / "ibovespa.parquet")["value"].to_list() == [162000.0]
    assert b3_indices.raw_path(2026, "IBXX").name == "ibxx_2026.json"


def test_b3_last_expected_session_skips_the_weekend() -> None:
    assert b3_indices.last_expected_session(2025) == date(2025, 12, 30)
    assert b3_indices.last_expected_session(2023) == date(2023, 12, 29)


def test_b3_refetch_rule_follows_the_file_not_the_run_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "B3_RAW_DIR", tmp_path)
    reference = date(2026, 3, 2)
    complete = b3_document({date(2025, 12, 22): "158.000,00", date(2025, 12, 30): "161.000,00"})
    partial = b3_document({date(2025, 12, 22): "158.000,00"})
    path = b3_indices.raw_path(2025)
    assert b3_indices.needs_fetch(2025, reference)
    write_with_mtime(path, partial, datetime(2025, 12, 23, 20))
    assert b3_indices.needs_fetch(2025, reference)
    write_with_mtime(path, complete, datetime(2025, 12, 30, 20))
    assert b3_indices.needs_fetch(2025, reference)
    write_with_mtime(path, partial, datetime(2026, 1, 5, 20))
    assert b3_indices.needs_fetch(2025, reference)
    write_with_mtime(path, complete, datetime(2026, 1, 5, 20))
    assert not b3_indices.needs_fetch(2025, reference)
    write_with_mtime(path, partial, datetime(2026, 1, 12, 20))
    assert not b3_indices.needs_fetch(2025, reference)
    write_with_mtime(b3_indices.raw_path(2026), partial, datetime(2026, 3, 1, 20))
    assert b3_indices.needs_fetch(2026, reference)


BCB_REPLY = b'[{"data":"02/09/2024","valor":"0.039270"}]'
BCB_INVALID = b"<html><head><title>Requisi\xc3\xa7\xc3\xa3o inv\xc3\xa1lida!</title></head></html>"


def bcb_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: list[bytes]) -> list[str]:
    monkeypatch.setattr(config, "BCB_RAW_DIR", tmp_path / "bcb")
    monkeypatch.setattr(config, "INDICES_PARQUET", tmp_path / "indices.parquet")
    pauses = []
    monkeypatch.setattr(bcb_sgs.time, "sleep", pauses.append)
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, content=replies[len(requested) - 1])

    mock_http(monkeypatch, handler)
    return requested


def test_bcb_retries_an_html_reply_and_saves_the_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requested = bcb_setup(tmp_path, monkeypatch, [BCB_INVALID, BCB_REPLY])
    indices = bcb_sgs.collect_bcb(date(2024, 9, 1), date(2024, 9, 3))
    assert len(requested) == 2
    assert (tmp_path / "bcb" / "sgs_12.json").read_bytes() == BCB_REPLY
    assert indices.height == 1


@pytest.mark.parametrize("invalid", [BCB_INVALID, b"[]", b'[{"data": "02/09/2024"}]', b'{"erro": "x"}'])
def test_bcb_gives_up_after_three_invalid_replies(invalid: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requested = bcb_setup(tmp_path, monkeypatch, [invalid] * 3)
    with pytest.raises(ValueError, match="not the series"):
        bcb_sgs.collect_bcb(date(2024, 9, 1), date(2024, 9, 3))
    assert len(requested) == 3
    assert not (tmp_path / "bcb" / "sgs_12.json").exists()


def test_bcb_invalid_replies_keep_the_previous_raw_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requested = bcb_setup(tmp_path, monkeypatch, [BCB_INVALID] * 3)
    raw = tmp_path / "bcb" / "sgs_12.json"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(BCB_REPLY)
    with pytest.raises(ValueError):
        bcb_sgs.collect_bcb(date(2024, 9, 1), date(2024, 9, 3))
    assert raw.read_bytes() == BCB_REPLY
    assert len(requested) == 3
