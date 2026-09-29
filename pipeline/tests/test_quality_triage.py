import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from pydantic import ValidationError

from fund_monitor import config
from fund_monitor.publish.site_json import open_issue_counts
from fund_monitor.quality.checks import ISSUE_SCHEMA, RULE_NAMES
from fund_monitor.quality.triage import OPEN_SEVERITIES, TriageEntry, TriageFile, apply_triage, load_triage


def issue_frame(rows: list[dict]) -> pl.DataFrame:
    defaults = {name: None for name in ISSUE_SCHEMA}
    return pl.DataFrame([{**defaults, "severity": "medium", **row} for row in rows], schema=ISSUE_SCHEMA)


def entry(**fields: object) -> TriageEntry:
    defaults = {
        "rule": "quota_jump",
        "series_id": None,
        "date_from": date(2024, 12, 9),
        "date_to": date(2024, 12, 9),
        "status": "explained",
        "note": "Evento de crédito.",
        "treated_on": date(2026, 9, 29),
    }
    return TriageEntry.model_validate({**defaults, **fields})


def test_missing_file_means_no_triage(tmp_path: Path) -> None:
    assert load_triage(tmp_path / "triage.json") == []


def test_load_triage_reads_the_entries(tmp_path: Path) -> None:
    path = tmp_path / "triage.json"
    path.write_text(json.dumps({"entries": [entry().model_dump(mode="json")]}), encoding="utf-8")
    (loaded,) = load_triage(path)
    assert loaded == entry()


def test_triage_rejects_unknown_fields_rules_and_statuses() -> None:
    with pytest.raises(ValidationError):
        TriageFile.model_validate({"entries": [], "extra": 1})
    with pytest.raises(ValidationError, match="unknown rule"):
        entry(rule="quota_jumps")
    with pytest.raises(ValidationError):
        entry(status="open")
    with pytest.raises(ValidationError, match="after date_to"):
        entry(date_from=date(2024, 12, 10))


def test_repository_triage_file_is_valid() -> None:
    entries = load_triage(config.TRIAGE_FILE)
    assert config.TRIAGE_FILE.exists()
    assert entries
    assert {item.rule for item in entries} <= set(RULE_NAMES)


def test_apply_triage_without_entries_leaves_everything_open() -> None:
    triaged = apply_triage(issue_frame([{"rule": "quota_jump", "series_id": "A", "date": date(2024, 12, 9)}]), [])
    assert triaged.columns == [*ISSUE_SCHEMA, "status", "note", "treated_on"]
    assert triaged.select("status", "note", "treated_on").row(0) == ("open", None, None)


def test_series_entry_and_wildcard_entry() -> None:
    issues = issue_frame(
        [
            {"rule": "quota_jump", "series_id": "A", "date": date(2024, 12, 9)},
            {"rule": "quota_jump", "series_id": "B", "date": date(2024, 12, 9)},
            {"rule": "zero_values", "series_id": "A", "date": date(2024, 12, 9)},
            {"rule": "zero_values", "series_id": "B", "date": date(2024, 12, 9)},
            {"rule": "quota_jump", "series_id": "A", "date": date(2024, 12, 10)},
        ]
    )
    entries = [entry(), entry(rule="zero_values", series_id="B", status="source_error", note="Linha zerada.")]
    assert apply_triage(issues, entries)["status"].to_list() == ["explained", "explained", "open", "source_error", "open"]


def test_period_rules_match_any_overlap() -> None:
    issues = issue_frame(
        [
            {"rule": "unexplained_net_assets", "series_id": "A", "date": date(2024, 8, 1), "end_date": date(2024, 8, 30)},
            {"rule": "unexplained_net_assets", "series_id": "A", "date": date(2024, 9, 1), "end_date": date(2024, 9, 30)},
            {"rule": "unexplained_net_assets", "series_id": "A", "date": date(2024, 10, 1), "end_date": date(2024, 10, 31)},
            {"rule": "missing_report", "series_id": "A", "date": date(2024, 8, 28), "end_date": date(2024, 9, 2)},
            {"rule": "missing_report", "series_id": "A", "date": None},
        ]
    )
    entries = [
        entry(rule="unexplained_net_assets", series_id="A", date_from=date(2024, 9, 15), date_to=date(2024, 10, 5), status="limitation"),
        entry(rule="missing_report", date_from=date(2024, 9, 1), date_to=date(2024, 9, 1), status="source_error"),
    ]
    assert apply_triage(issues, entries)["status"].to_list() == ["open", "limitation", "limitation", "source_error", "open"]


def test_specific_entry_wins_then_the_most_recent() -> None:
    issues = issue_frame(
        [
            {"rule": "quota_jump", "series_id": "A", "date": date(2024, 12, 9)},
            {"rule": "quota_jump", "series_id": "B", "date": date(2024, 12, 9)},
        ]
    )
    entries = [
        entry(series_id="A", status="source_error", note="Antiga.", treated_on=date(2026, 1, 1)),
        entry(status="explained", note="Curinga.", treated_on=date(2026, 9, 29)),
        entry(series_id="A", status="limitation", note="Recente.", treated_on=date(2026, 6, 1)),
        entry(status="source_error", note="Curinga antigo.", treated_on=date(2025, 1, 1)),
    ]
    triaged = apply_triage(issues, entries)
    assert triaged.select("series_id", "status", "note", "treated_on").rows() == [
        ("A", "limitation", "Recente.", date(2026, 6, 1)),
        ("B", "explained", "Curinga.", date(2026, 9, 29)),
    ]


def test_info_issues_are_never_counted_as_open() -> None:
    issues = issue_frame(
        [
            {"rule": "short_history", "series_id": "A", "severity": "info", "date": date(2025, 1, 2)},
            {"rule": "quota_jump", "series_id": "A", "severity": "info", "date": date(2025, 12, 5)},
            {"rule": "quota_jump", "series_id": "B", "severity": "medium", "date": date(2025, 12, 5)},
            {"rule": "zero_values", "series_id": "B", "severity": "high", "date": date(2025, 12, 5)},
        ]
    )
    triaged = apply_triage(issues, [entry(rule="zero_values", date_from=date(2025, 12, 5), date_to=date(2025, 12, 5), status="source_error")])
    assert triaged["status"].to_list() == ["open", "open", "open", "source_error"]
    counts = open_issue_counts(triaged)
    assert (counts.high, counts.medium, counts.low, counts.info) == (0, 1, 0, 0)
    assert OPEN_SEVERITIES == ("high", "medium", "low")
