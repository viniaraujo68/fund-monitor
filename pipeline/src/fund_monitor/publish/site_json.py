import json
import logging
import math
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict

from fund_monitor import config
from fund_monitor.calc.benchmarks import BENCHMARKS_BY_CLASSIFICATION, MARKET_BENCHMARK_BY_CLASSIFICATION
from fund_monitor.calc.returns import MONTHLY_WINDOWS, SINCE_START
from fund_monitor.calc.series import series_id
from fund_monitor.publish.names import is_structural_vehicle, unique_display_names
from fund_monitor.quality.checks import SEVERITIES
from fund_monitor.universe import GENERAL_PUBLIC, select_manager_series, select_monitored_series, select_peer_universe

logger = logging.getLogger(__name__)

RETURN_DIGITS = 6
RATIO_DIGITS = 4
MONEY_DIGITS = 2
INDEX_DIGITS = 4
WINDOWS = ("mtd", "ytd", *MONTHLY_WINDOWS, SINCE_START)
FUNDS_DIRECTORY = "funds"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceStatus(Contract):
    source: str
    last_date: date | None


class QualitySummary(Contract):
    checked_series: int
    checked_days: int
    by_severity: dict[str, int]
    by_rule: dict[str, int]


class UniverseCounts(Contract):
    manager_series: int
    exclusive_series: int
    monitored_series: int
    general_public_series: int
    peer_candidates: int
    peer_eligible: int


class Meta(Contract):
    generated_at: datetime
    reference_date: date
    as_of: date
    window_start: date
    manager_cnpj: str
    manager_name: str
    universe: UniverseCounts
    sources: list[SourceStatus]
    quality: QualitySummary
    windows: list[str]


class IssueCounts(Contract):
    high: int
    medium: int
    low: int
    info: int


class FundSummary(Contract):
    series_id: str
    cnpj: str
    subclass_id: str | None
    display_name: str
    class_name: str
    subclass_name: str | None
    cvm_classification: str | None
    anbima_classification: str | None
    target_audience: str | None
    condominium: str | None
    performance_benchmark: str | None
    structural_vehicle: bool
    benchmarks: list[str]
    market_benchmark: str | None
    first_date: date | None
    last_date: date | None
    inherited_until: date | None
    net_assets: float | None
    shareholders: int | None
    net_flow_12m: float | None
    flow_window_partial: bool | None
    return_mtd: float | None
    return_ytd: float | None
    return_12m: float | None
    return_24m: float | None
    cdi_12m: float | None
    pct_cdi_12m: float | None
    volatility_12m: float | None
    max_drawdown_12m: float | None
    sharpe_12m: float | None
    peer_count: int
    peer_return_percentile_12m: float | None
    issues: IssueCounts


class WindowRow(Contract):
    window: str
    base_date: date | None
    end_date: date | None
    business_days: int | None
    fund_return: float | None
    fund_annualized: float | None
    cdi_return: float | None
    cdi_annualized: float | None
    pct_cdi: float | None
    benchmark_returns: dict[str, float | None]


class RiskRow(Contract):
    window: str
    observations: int
    volatility: float | None
    sharpe: float | None
    max_drawdown: float | None
    peak_date: date | None
    trough_date: date | None
    recovery_date: date | None
    positive_days_share: float | None
    best_day: float | None
    best_day_date: date | None
    worst_day: float | None
    worst_day_date: date | None
    beta: float | None
    tracking_error: float | None


class Series(Contract):
    dates: list[date]
    values: dict[str, list[float | None]]


class RollingRow(Contract):
    month: date
    end_date: date
    fund_return: float | None
    cdi_return: float | None


class FlowRow(Contract):
    month: date
    net_flow: float | None
    inflows: float | None
    outflows: float | None
    net_assets_end: float | None
    shareholders_end: int | None
    monthly_return: float | None
    unexplained_share: float | None


class PeerMetric(Contract):
    value: float | None
    percentile: float | None
    p25: float | None
    median: float | None
    p75: float | None


class PeerPosition(Contract):
    anbima_classification: str
    target_audience: str
    peer_count: int
    metrics: dict[str, PeerMetric]


class Issue(Contract):
    rule: str
    severity: str
    series_id: str | None
    display_name: str | None
    date: date | None
    end_date: date | None
    days: int | None
    value: float | None
    threshold: float | None
    detail: str | None


class FundDetail(Contract):
    summary: FundSummary
    windows: list[WindowRow]
    risk: list[RiskRow]
    cumulative: Series
    drawdown: Series
    rolling_12m: list[RollingRow]
    monthly_flows: list[FlowRow]
    peers: PeerPosition | None
    issues: list[Issue]


class AggregateRow(Contract):
    scope: str
    group: str
    group_value: str | None
    month: date
    net_flow: float
    net_assets_end: float
    classes: int


class AggregateTotal(Contract):
    scope: str
    as_of: date
    net_assets: float
    net_flow_12m: float
    classes: int


class Aggregates(Contract):
    totals: list[AggregateTotal]
    monthly: list[AggregateRow]


class QualityDocument(Contract):
    summary: QualitySummary
    issues: list[Issue]


def rounded(value: float | None, digits: int) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits) + 0.0


def load_metrics() -> dict[str, pl.DataFrame]:
    return {path.stem: pl.read_parquet(path) for path in config.METRICS_DIR.glob("*.parquet")}


def fund_attributes(registry: pl.DataFrame) -> pl.DataFrame:
    monitored = select_monitored_series(registry, config.MANAGER_CNPJ).with_columns(series_id()).sort("series_id")
    names = unique_display_names(monitored.select("class_name", "subclass_name").rows())
    return monitored.with_columns(
        pl.Series("display_name", names),
        pl.col("class_name").map_elements(is_structural_vehicle, return_dtype=pl.Boolean).alias("structural_vehicle"),
    )


def by_series(frame: pl.DataFrame) -> dict[str, pl.DataFrame]:
    return {key: group for (key,), group in frame.partition_by("series_id", as_dict=True).items()}


def issue_counts(issues: pl.DataFrame) -> IssueCounts:
    counts = dict(issues.group_by("severity").len().iter_rows()) if issues.height else {}
    return IssueCounts(**{severity: counts.get(severity, 0) for severity in SEVERITIES})


def window_value(windows: pl.DataFrame, window: str, column: str, digits: int = RETURN_DIGITS) -> float | None:
    row = windows.filter(pl.col("window") == window)
    return rounded(row[column].item(), digits) if row.height else None


def risk_value(risk: pl.DataFrame, window: str, column: str, digits: int = RETURN_DIGITS) -> float | None:
    row = risk.filter(pl.col("window") == window)
    return rounded(row[column].item(), digits) if row.height else None


def build_summary(
    attributes: dict,
    windows: pl.DataFrame,
    risk: pl.DataFrame,
    flows: dict | None,
    cumulative: pl.DataFrame,
    position: dict | None,
    issues: pl.DataFrame,
) -> FundSummary:
    classification = attributes["cvm_classification"]
    inherited = cumulative.filter(pl.col("inherited"))
    since_start = windows.filter(pl.col("window") == SINCE_START)
    return FundSummary(
        series_id=attributes["series_id"],
        cnpj=attributes["cnpj"],
        subclass_id=attributes["subclass_id"],
        display_name=attributes["display_name"],
        class_name=attributes["class_name"],
        subclass_name=attributes["subclass_name"],
        cvm_classification=classification,
        anbima_classification=attributes["anbima_classification"],
        target_audience=attributes["target_audience"],
        condominium=attributes["condominium"],
        performance_benchmark=attributes["performance_benchmark"],
        structural_vehicle=attributes["structural_vehicle"],
        benchmarks=list(BENCHMARKS_BY_CLASSIFICATION.get(classification, ("cdi",))),
        market_benchmark=MARKET_BENCHMARK_BY_CLASSIFICATION.get(classification),
        first_date=since_start["first_date"].item() if since_start.height else None,
        last_date=since_start["last_date"].item() if since_start.height else None,
        inherited_until=inherited["date"].max() if inherited.height else None,
        net_assets=rounded(flows["net_assets"], MONEY_DIGITS) if flows else None,
        shareholders=flows["shareholders"] if flows else None,
        net_flow_12m=rounded(flows["net_flow_12m"], MONEY_DIGITS) if flows else None,
        flow_window_partial=flows["flow_window_partial"] if flows else None,
        return_mtd=window_value(windows, "mtd", "fund_return"),
        return_ytd=window_value(windows, "ytd", "fund_return"),
        return_12m=window_value(windows, "12m", "fund_return"),
        return_24m=window_value(windows, "24m", "fund_return"),
        cdi_12m=window_value(windows, "12m", "cdi_return"),
        pct_cdi_12m=window_value(windows, "12m", "pct_cdi", RATIO_DIGITS),
        volatility_12m=risk_value(risk, "12m", "volatility"),
        max_drawdown_12m=risk_value(risk, "12m", "max_drawdown"),
        sharpe_12m=risk_value(risk, "12m", "sharpe", RATIO_DIGITS),
        peer_count=position["peer_count"] if position else 0,
        peer_return_percentile_12m=rounded(position["fund_return_percentile"], RATIO_DIGITS) if position else None,
        issues=issue_counts(issues),
    )


def build_windows(windows: pl.DataFrame, benchmarks: list[str]) -> list[WindowRow]:
    market = [b for b in benchmarks if b != "cdi"]
    rows = {row["window"]: row for row in windows.iter_rows(named=True)}
    return [
        WindowRow(
            window=window,
            base_date=row["base_date"] if row["has_history"] else None,
            end_date=row["end_date"],
            business_days=row["business_days"] if row["has_history"] else None,
            fund_return=rounded(row["fund_return"], RETURN_DIGITS),
            fund_annualized=rounded(row["fund_annualized"], RETURN_DIGITS),
            cdi_return=rounded(row["cdi_return"], RETURN_DIGITS) if row["has_history"] else None,
            cdi_annualized=rounded(row["cdi_annualized"], RETURN_DIGITS),
            pct_cdi=rounded(row["pct_cdi"], RATIO_DIGITS),
            benchmark_returns={b: rounded(row[f"{b}_return"], RETURN_DIGITS) if row["has_history"] else None for b in market},
        )
        for window in WINDOWS
        if (row := rows.get(window)) is not None
    ]


def build_risk(risk: pl.DataFrame, market_benchmark: str | None) -> list[RiskRow]:
    return [
        RiskRow(
            window=row["window"],
            observations=row["observations"],
            volatility=rounded(row["volatility"], RETURN_DIGITS),
            sharpe=rounded(row["sharpe"], RATIO_DIGITS),
            max_drawdown=rounded(row["max_drawdown"], RETURN_DIGITS),
            peak_date=row["peak_date"],
            trough_date=row["trough_date"],
            recovery_date=row["recovery_date"],
            positive_days_share=rounded(row["positive_days_share"], RATIO_DIGITS),
            best_day=rounded(row["best_day"], RETURN_DIGITS),
            best_day_date=row["best_day_date"],
            worst_day=rounded(row["worst_day"], RETURN_DIGITS),
            worst_day_date=row["worst_day_date"],
            beta=rounded(row[f"beta_{market_benchmark}"], RATIO_DIGITS) if market_benchmark else None,
            tracking_error=rounded(row[f"tracking_error_{market_benchmark}"], RETURN_DIGITS) if market_benchmark else None,
        )
        for row in risk.sort("window").iter_rows(named=True)
    ]


def build_series(frame: pl.DataFrame, columns: dict[str, str], digits: int) -> Series:
    ordered = frame.sort("date")
    return Series(
        dates=ordered["date"].to_list(),
        values={label: [rounded(v, digits) for v in ordered[column].to_list()] for label, column in columns.items()},
    )


def build_rolling(rolling: pl.DataFrame) -> list[RollingRow]:
    return [
        RollingRow(
            month=row["month"],
            end_date=row["end_date"],
            fund_return=rounded(row["fund_return"], RETURN_DIGITS),
            cdi_return=rounded(row["cdi_return"], RETURN_DIGITS),
        )
        for row in rolling.sort("month").iter_rows(named=True)
    ]


def build_flows(flows: pl.DataFrame) -> list[FlowRow]:
    return [
        FlowRow(
            month=row["month"],
            net_flow=rounded(row["net_flow"], MONEY_DIGITS),
            inflows=rounded(row["inflows"], MONEY_DIGITS),
            outflows=rounded(row["outflows"], MONEY_DIGITS),
            net_assets_end=rounded(row["net_assets_end"], MONEY_DIGITS),
            shareholders_end=row["shareholders_end"],
            monthly_return=rounded(row["monthly_return"], RETURN_DIGITS),
            unexplained_share=rounded(row["unexplained_share"], RATIO_DIGITS),
        )
        for row in flows.sort("month").iter_rows(named=True)
    ]


def build_peer_position(position: dict | None, subject: dict) -> PeerPosition | None:
    if position is None or position["peer_count"] == 0:
        return None
    return PeerPosition(
        anbima_classification=position["anbima_classification"],
        target_audience=position["target_audience"],
        peer_count=position["peer_count"],
        metrics={
            metric: PeerMetric(
                value=rounded(subject.get(metric), RETURN_DIGITS),
                percentile=rounded(position[f"{metric}_percentile"], RATIO_DIGITS),
                p25=rounded(position[f"{metric}_p25"], RETURN_DIGITS),
                median=rounded(position[f"{metric}_median"], RETURN_DIGITS),
                p75=rounded(position[f"{metric}_p75"], RETURN_DIGITS),
            )
            for metric in ("fund_return", "volatility", "max_drawdown")
        },
    )


def build_issues(issues: pl.DataFrame, names: dict[str, str]) -> list[Issue]:
    return [
        Issue(
            rule=row["rule"],
            severity=row["severity"],
            series_id=row["series_id"],
            display_name=names.get(row["series_id"]) if row["series_id"] else None,
            date=row["date"],
            end_date=row["end_date"],
            days=row["days"],
            value=rounded(row["value"], RETURN_DIGITS),
            threshold=rounded(row["threshold"], RETURN_DIGITS),
            detail=row["detail"],
        )
        for row in issues.iter_rows(named=True)
    ]


def quality_summary(issues: pl.DataFrame, metrics: dict[str, pl.DataFrame]) -> QualitySummary:
    coverage = metrics["quality_checked_days"].row(0, named=True)
    by_severity = dict(issues.group_by("severity").len().iter_rows()) if issues.height else {}
    return QualitySummary(
        checked_series=coverage["checked_series"],
        checked_days=coverage["checked_days"],
        by_severity={severity: by_severity.get(severity, 0) for severity in SEVERITIES},
        by_rule=dict(issues.group_by("rule").len().sort("rule").iter_rows()) if issues.height else {},
    )


def write_json(path: Path, document: Contract | list[Contract]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(document, list):
        payload = json.dumps([item.model_dump(mode="json") for item in document], ensure_ascii=False, separators=(",", ":"))
    else:
        payload = document.model_dump_json()
    path.write_text(payload, encoding="utf-8")


def publish_site(registry: pl.DataFrame, reference_date: date) -> None:
    metrics = load_metrics()
    attributes = fund_attributes(registry)
    names = dict(attributes.select("series_id", "display_name").iter_rows())
    windows = by_series(metrics["window_returns"])
    risks = by_series(metrics["risk"])
    cumulative = by_series(metrics["cumulative_index"])
    drawdowns = by_series(metrics["drawdown"])
    rolling = by_series(metrics["rolling_12m"])
    monthly = by_series(metrics["monthly_flows"])
    flows = {row["series_id"]: row for row in metrics["flow_summary"].iter_rows(named=True)}
    positions = {row["series_id"]: row for row in metrics["peer_positions"].iter_rows(named=True)}
    issues = metrics["quality_issues"]
    issues_by_series = by_series(issues.filter(pl.col("series_id").is_not_null()))
    empty_issues = issues.clear()
    empty = {name: frame.clear() for name, frame in metrics.items()}

    summaries, details = [], {}
    for attribute in attributes.iter_rows(named=True):
        key = attribute["series_id"]
        fund_windows = windows.get(key, empty["window_returns"])
        fund_risk = risks.get(key, empty["risk"])
        fund_cumulative = cumulative.get(key, empty["cumulative_index"])
        fund_issues = issues_by_series.get(key, empty_issues)
        summary = build_summary(attribute, fund_windows, fund_risk, flows.get(key), fund_cumulative, positions.get(key), fund_issues)
        benchmarks = summary.benchmarks
        subject = {
            "fund_return": summary.return_12m,
            "volatility": summary.volatility_12m,
            "max_drawdown": summary.max_drawdown_12m,
        }
        summaries.append(summary)
        details[key] = FundDetail(
            summary=summary,
            windows=build_windows(fund_windows, benchmarks),
            risk=build_risk(fund_risk, summary.market_benchmark),
            cumulative=build_series(
                fund_cumulative, {"fund": "fund_index", **{b: f"{b}_index" for b in benchmarks}}, INDEX_DIGITS
            ),
            drawdown=build_series(drawdowns.get(key, empty["drawdown"]), {"fund": "drawdown"}, RETURN_DIGITS),
            rolling_12m=build_rolling(rolling.get(key, empty["rolling_12m"])),
            monthly_flows=build_flows(monthly.get(key, empty["monthly_flows"])),
            peers=build_peer_position(positions.get(key), subject),
            issues=build_issues(fund_issues, names),
        )

    manager = select_manager_series(registry, config.MANAGER_CNPJ)
    summary = quality_summary(issues, metrics)
    source_dates = metrics["quality_source_dates"].row(0, named=True)
    meta = Meta(
        generated_at=datetime.now(timezone.utc),
        reference_date=reference_date,
        as_of=metrics["window_returns"]["end_date"].max(),
        window_start=config.WINDOW_START,
        manager_cnpj=config.MANAGER_CNPJ,
        manager_name=manager["manager_names"].explode().filter(manager["manager_cnpjs"].explode() == config.MANAGER_CNPJ).first(),
        universe=UniverseCounts(
            manager_series=manager.height,
            exclusive_series=manager.filter(pl.col("exclusive")).height,
            monitored_series=attributes.height,
            general_public_series=attributes.filter(pl.col("target_audience") == GENERAL_PUBLIC).height,
            peer_candidates=select_peer_universe(registry, config.MANAGER_CNPJ).height,
            peer_eligible=metrics["peers"]["eligible"].sum(),
        ),
        sources=[SourceStatus(source=source, last_date=last_date) for source, last_date in source_dates.items()],
        quality=summary,
        windows=list(WINDOWS),
    )
    aggregates = Aggregates(
        totals=[AggregateTotal(**{**row, "net_assets": rounded(row["net_assets"], MONEY_DIGITS), "net_flow_12m": rounded(row["net_flow_12m"], MONEY_DIGITS)}) for row in metrics["aggregate_totals"].iter_rows(named=True)],
        monthly=[
            AggregateRow(**{**row, "net_flow": rounded(row["net_flow"], MONEY_DIGITS), "net_assets_end": rounded(row["net_assets_end"], MONEY_DIGITS)})
            for row in metrics["aggregate_monthly"].iter_rows(named=True)
        ],
    )

    if config.SITE_DIR.exists():
        shutil.rmtree(config.SITE_DIR)
    write_json(config.SITE_DIR / "meta.json", meta)
    write_json(config.SITE_DIR / "funds.json", summaries)
    write_json(config.SITE_DIR / "aggregates.json", aggregates)
    write_json(config.SITE_DIR / "quality.json", QualityDocument(summary=summary, issues=build_issues(issues, names)))
    for key, detail in details.items():
        write_json(config.SITE_DIR / FUNDS_DIRECTORY / f"{key}.json", detail)
    logger.info("site: %d funds, %d issues written to %s", len(summaries), issues.height, config.SITE_DIR)
