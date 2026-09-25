from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from fund_monitor.calc.flows import aggregate_monthly, flow_summary, monthly_flows


def rows_frame(records: list[tuple]) -> pl.DataFrame:
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
