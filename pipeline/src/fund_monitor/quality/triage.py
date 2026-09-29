from datetime import date
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from fund_monitor.quality.checks import HIGH, LOW, MEDIUM, RULE_NAMES

OPEN = "open"
EXPLAINED = "explained"
SOURCE_ERROR = "source_error"
LIMITATION = "limitation"
STATUSES = (OPEN, EXPLAINED, SOURCE_ERROR, LIMITATION)
OPEN_SEVERITIES = (HIGH, MEDIUM, LOW)

TRIAGE_SCHEMA = {
    "rule": pl.String,
    "series_id": pl.String,
    "date_from": pl.Date,
    "date_to": pl.Date,
    "status": pl.String,
    "note": pl.String,
    "treated_on": pl.Date,
}


class TriageEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule: str
    series_id: str | None
    date_from: date
    date_to: date
    status: Literal["explained", "source_error", "limitation"]
    note: str
    treated_on: date

    @field_validator("rule")
    @classmethod
    def known_rule(cls, rule: str) -> str:
        if rule not in RULE_NAMES:
            raise ValueError(f"unknown rule {rule!r}")
        return rule

    @model_validator(mode="after")
    def ordered_period(self) -> "TriageEntry":
        if self.date_from > self.date_to:
            raise ValueError(f"date_from {self.date_from} is after date_to {self.date_to}")
        return self


class TriageFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[TriageEntry]


def load_triage(path: Path) -> list[TriageEntry]:
    if not path.exists():
        return []
    return TriageFile.model_validate_json(path.read_text(encoding="utf-8")).entries


def is_open() -> pl.Expr:
    return (pl.col("status") == OPEN) & pl.col("severity").is_in(OPEN_SEVERITIES)


def apply_triage(issues: pl.DataFrame, entries: list[TriageEntry]) -> pl.DataFrame:
    triage = pl.DataFrame([entry.model_dump() for entry in entries], schema=TRIAGE_SCHEMA).with_row_index("entry")
    indexed = issues.with_row_index("issue")
    series_matches = pl.col("entry_series_id").is_null() | (pl.col("entry_series_id") == pl.col("series_id")).fill_null(False)
    period_overlaps = (pl.col("date") <= pl.col("date_to")) & (pl.coalesce("end_date", "date") >= pl.col("date_from"))
    matches = (
        indexed.select("issue", "rule", "series_id", "date", "end_date")
        .join(triage.rename({"series_id": "entry_series_id"}), on="rule")
        .filter(series_matches, period_overlaps.fill_null(False))
        .sort(
            "issue",
            pl.col("entry_series_id").is_not_null(),
            "treated_on",
            "entry",
            descending=[False, True, True, True],
        )
        .unique("issue", keep="first", maintain_order=True)
        .select("issue", "status", "note", "treated_on")
    )
    return (
        indexed.join(matches, on="issue", how="left")
        .sort("issue")
        .with_columns(pl.col("status").fill_null(OPEN))
        .drop("issue")
    )
