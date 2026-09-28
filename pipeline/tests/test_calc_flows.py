from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from fund_monitor.calc.flows import aggregate_monthly, aggregate_totals, flow_summary, monthly_flows


def rows_frame(records: list[tuple], subclass_id: str | None = None) -> pl.DataFrame:
    return pl.DataFrame(
        records,
        schema={
            "series_id": pl.String,
            "cnpj": pl.String,
            "date": pl.Date,
            "net_assets": pl.Decimal(20, 2),
            "inflows": pl.Decimal(20, 2),
            "outflows": pl.Decimal(20, 2),
            "shareholders": pl.Int64,
        },
        orient="row",
    ).with_columns(subclass_id=pl.lit(subclass_id, dtype=pl.String))


def subclass_rows(subclass_id: str | None, records: list[tuple[date, int, int]]) -> pl.DataFrame:
    key = "X" if subclass_id is None else f"X-{subclass_id}"
    return rows_frame(
        [(key, "X", day, Decimal(assets), Decimal(flow), Decimal("0"), 1) for day, assets, flow in records],
        subclass_id,
    )


def quotas_for(records: list[tuple]) -> pl.DataFrame:
    return pl.DataFrame(records, schema={"series_id": pl.String, "date": pl.Date, "quota_value": pl.Decimal(28, 12)}, orient="row")


ROWS = rows_frame(
    [
        ("A", "A", date(2026, 1, 30), Decimal("1000"), Decimal("0"), Decimal("0"), 10),
        ("A", "A", date(2026, 2, 10), Decimal("1080"), Decimal("80"), Decimal("30"), 11),
        ("A", "A", date(2026, 2, 27), Decimal("1100"), Decimal("0"), Decimal("0"), 12),
        ("A", "A", date(2026, 3, 31), Decimal("1300"), Decimal("100"), Decimal("0"), 15),
    ]
)
QUOTAS = quotas_for(
    [
        ("A", date(2026, 1, 30), Decimal("2.0")),
        ("A", date(2026, 2, 27), Decimal("2.1")),
        ("A", date(2026, 3, 31), Decimal("2.1")),
    ]
)


def test_monthly_decomposition_explains_change_with_flow_and_return() -> None:
    february = monthly_flows(ROWS, QUOTAS).filter(pl.col("month") == date(2026, 2, 1)).row(0, named=True)
    assert february["net_flow"] == pytest.approx(50)
    assert february["monthly_return"] == pytest.approx(0.05)
    assert february["unexplained_change"] == pytest.approx(1100 - 1000 - 50 - 1000 * 0.05)
    assert february["unexplained_share"] == pytest.approx(0.0)


def test_monthly_decomposition_exposes_unexplained_change() -> None:
    march = monthly_flows(ROWS, QUOTAS).filter(pl.col("month") == date(2026, 3, 1)).row(0, named=True)
    assert march["unexplained_change"] == pytest.approx(1300 - 1100 - 100 - 0)
    assert march["unexplained_share"] == pytest.approx(100 / 1100)


def test_flow_summary_marks_partial_window() -> None:
    summary = flow_summary(ROWS, as_of=date(2026, 3, 31)).row(0, named=True)
    assert summary["net_flow_12m"] == pytest.approx(150)
    assert summary["net_assets"] == pytest.approx(1300)
    assert summary["shareholders"] == 15
    assert summary["flow_window_partial"] is True
    assert summary["shareholders_12m_ago"] is None


def test_aggregate_sums_classes_by_label() -> None:
    other = rows_frame([("B", "B", date(2026, 2, 27), Decimal("500"), Decimal("20"), Decimal("5"), 3)])
    attributes = pl.DataFrame({"cnpj": ["A", "B"], "cvm_classification": ["Renda Fixa", "Renda Fixa"]})
    aggregate = aggregate_monthly(pl.concat([ROWS, other]), attributes, "cvm_classification")
    february = aggregate.filter(pl.col("month") == date(2026, 2, 1)).row(0, named=True)
    assert february["net_flow"] == pytest.approx(65)
    assert february["net_assets_end"] == pytest.approx(1600)
    assert february["classes"] == 2


def test_aggregate_rejects_subclass_level_labels() -> None:
    attributes = pl.DataFrame({"cnpj": ["A", "A"], "target_audience": ["Público Geral", "Profissional"]})
    with pytest.raises(ValueError, match="class-level labels"):
        aggregate_monthly(ROWS, attributes, "target_audience")


def test_aggregate_totals_use_last_report_and_twelve_month_flows() -> None:
    other = rows_frame([("B", "B", date(2026, 2, 27), Decimal("500"), Decimal("20"), Decimal("5"), 3)])
    totals = aggregate_totals(pl.concat([ROWS, other]), as_of=date(2026, 3, 31))
    assert totals == {"net_assets": pytest.approx(1800), "net_flow_12m": pytest.approx(165), "classes": 2}


def test_aggregates_keep_the_last_report_of_each_subclass() -> None:
    rows = pl.concat(
        [
            subclass_rows("A", [(date(2026, 9, 23), 1000, 0), (date(2026, 9, 24), 1010, 0)]),
            subclass_rows("B", [(date(2026, 9, 23), 500, 0)]),
        ]
    )
    totals = aggregate_totals(rows, as_of=date(2026, 9, 24))
    assert totals["net_assets"] == pytest.approx(1510)
    assert totals["classes"] == 1
    attributes = pl.DataFrame({"cnpj": ["X"], "cvm_classification": ["Renda Fixa"]})
    september = aggregate_monthly(rows, attributes, "cvm_classification").row(0, named=True)
    assert september["net_assets_end"] == pytest.approx(1510)
    assert september["classes"] == 1


def test_aggregates_drop_the_class_row_once_subclasses_report() -> None:
    rows = pl.concat(
        [
            subclass_rows(None, [(date(2026, 6, 15), 900, 40), (date(2026, 6, 16), 960, 50)]),
            subclass_rows("A", [(date(2026, 6, 17), 700, 10)]),
            subclass_rows("B", [(date(2026, 6, 17), 300, 5)]),
        ]
    )
    attributes = pl.DataFrame({"cnpj": ["X"], "cvm_classification": ["Renda Fixa"]})
    june = aggregate_monthly(rows, attributes, "cvm_classification").row(0, named=True)
    assert june["net_assets_end"] == pytest.approx(1000)
    assert june["net_flow"] == pytest.approx(105)
    assert aggregate_totals(rows, as_of=date(2026, 6, 17))["net_assets"] == pytest.approx(1000)
    assert aggregate_totals(rows, as_of=date(2026, 6, 16))["net_assets"] == pytest.approx(960)


YEAR_ROWS = rows_frame(
    [
        ("A", "A", date(2025, 3, 31), Decimal("800"), Decimal("70"), Decimal("0"), 8),
        ("A", "A", date(2025, 4, 1), Decimal("820"), Decimal("20"), Decimal("0"), 9),
        ("A", "A", date(2026, 3, 31), Decimal("1000"), Decimal("0"), Decimal("30"), 12),
    ]
)


def test_flow_summary_over_a_full_twelve_month_window() -> None:
    summary = flow_summary(YEAR_ROWS, as_of=date(2026, 3, 31)).row(0, named=True)
    assert summary["flow_window_partial"] is False
    assert summary["net_flow_12m"] == pytest.approx(20 - 30)
    assert summary["net_assets_12m_ago"] == pytest.approx(800)
    assert summary["shareholders_12m_ago"] == 8
    assert summary["net_assets_change_12m"] == pytest.approx(1000 / 800 - 1)
    assert summary["shareholders_change_12m"] == 4


def test_aggregate_totals_leave_flows_older_than_twelve_months_out() -> None:
    totals = aggregate_totals(YEAR_ROWS, as_of=date(2026, 3, 31))
    assert totals["net_flow_12m"] == pytest.approx(20 - 30)
    assert totals["net_assets"] == pytest.approx(1000)
