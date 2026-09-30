import json
import logging
import math
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl
from pydantic import BaseModel, ConfigDict, TypeAdapter

from fund_monitor import config
from fund_monitor.calc.benchmarks import BENCHMARKS_BY_CLASSIFICATION, CDI, IBRX, MARKET_BENCHMARK_BY_CLASSIFICATION
from fund_monitor.calc.peers import MIN_PEERS, PEER_METRICS
from fund_monitor.calc.returns import MONTHLY_WINDOWS, SINCE_START
from fund_monitor.calc.series import series_id
from fund_monitor.publish.names import unique_display_names
from fund_monitor.quality.checks import INFO, SEVERITIES
from fund_monitor.quality.report import COVERAGE_METRIC, ISSUES_METRIC, SOURCES_METRIC
from fund_monitor.quality.triage import OPEN, OPEN_SEVERITIES, STATUSES, apply_triage, is_open, load_triage
from fund_monitor.universe import GENERAL_PUBLIC, is_structural, select_manager_series, select_monitored_series, select_peer_universe

logger = logging.getLogger(__name__)

RETURN_DIGITS = 6
RATIO_DIGITS = 4
MONEY_DIGITS = 2
INDEX_DIGITS = 4
WINDOWS = ("mtd", "ytd", *MONTHLY_WINDOWS, SINCE_START)
FUNDS_DIRECTORY = "funds"
DI_BENCHMARK = "DI de um dia"
IBRX_BENCHMARK = "IBrX"
EQUITIES = "Ações"
EVENT_RULE = "quota_jump"
EVENT_MIN_SERIES = 3


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
    open_by_severity: dict[str, int]
    by_status: dict[str, int]
    treated: int


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
    primary_benchmark: str
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
    primary_benchmark_12m: float | None
    excess_primary_12m: float | None
    volatility_12m: float | None
    max_drawdown_12m: float | None
    sharpe_12m: float | None
    peer_count: int
    peer_return_percentile_12m: float | None
    peer_volatility_percentile_12m: float | None
    issues: IssueCounts
    open_issues: IssueCounts


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
    excess_returns: dict[str, float | None]


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
    deviation: float | None
    detail: str | None
    status: str
    note: str | None
    treated_on: date | None


class QualityEvent(Contract):
    rule: str
    date: date
    severity: str
    status: str
    note: str | None
    series_ids: list[str]
    display_names: list[str]
    cnpj_count: int


class FundDetail(Contract):
    summary: FundSummary
    windows: list[WindowRow]
    risk: list[RiskRow]
    cumulative: Series
    drawdown: Series
    monthly_flows: list[FlowRow]
    peers: PeerPosition | None
    issues: list[Issue]


class AggregateRow(Contract):
    scope: str
    structural: bool
    group: str
    group_value: str | None
    month: date
    net_flow: float
    net_assets_end: float
    classes: int


class AggregateTotal(Contract):
    scope: str
    structural: bool
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
    events: list[QualityEvent]


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
        is_structural().alias("structural_vehicle"),
    )


def by_series(frame: pl.DataFrame) -> dict[str, pl.DataFrame]:
    return {key: group for (key,), group in frame.partition_by("series_id", as_dict=True).items()}


def issue_counts(issues: pl.DataFrame) -> IssueCounts:
    counts = dict(issues.group_by("severity").len().iter_rows()) if issues.height else {}
    return IssueCounts(**{severity: counts.get(severity, 0) for severity in SEVERITIES})


def open_issue_counts(issues: pl.DataFrame) -> IssueCounts:
    return issue_counts(issues.filter(is_open()))


def severity_rank() -> pl.Expr:
    return pl.col("severity").replace_strict({s: rank for rank, s in enumerate(SEVERITIES)}, return_dtype=pl.Int8)


def window_value(frame: pl.DataFrame, window: str, column: str, digits: int = RETURN_DIGITS) -> float | None:
    row = frame.filter(pl.col("window") == window)
    return rounded(row[column].item(), digits) if row.height else None


def series_benchmarks(classification: str | None, performance_benchmark: str | None) -> tuple[list[str], str | None]:
    if performance_benchmark == DI_BENCHMARK:
        return [CDI], None
    if classification == EQUITIES and performance_benchmark == IBRX_BENCHMARK:
        return [CDI, IBRX], IBRX
    return list(BENCHMARKS_BY_CLASSIFICATION.get(classification, (CDI,))), MARKET_BENCHMARK_BY_CLASSIFICATION.get(classification)


def build_summary(
    attributes: dict,
    windows: pl.DataFrame,
    risk: pl.DataFrame,
    flows: dict | None,
    position: dict | None,
    issues: pl.DataFrame,
) -> FundSummary:
    classification = attributes["cvm_classification"]
    benchmarks, market_benchmark = series_benchmarks(classification, attributes["performance_benchmark"])
    primary_benchmark = market_benchmark or CDI
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
        benchmarks=benchmarks,
        market_benchmark=market_benchmark,
        primary_benchmark=primary_benchmark,
        first_date=since_start["first_date"].item() if since_start.height else None,
        last_date=since_start["last_date"].item() if since_start.height else None,
        inherited_until=since_start["inherited_until"].item() if since_start.height else None,
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
        primary_benchmark_12m=window_value(windows, "12m", f"{primary_benchmark}_return"),
        excess_primary_12m=window_value(windows, "12m", f"excess_{primary_benchmark}"),
        volatility_12m=window_value(risk, "12m", "volatility"),
        max_drawdown_12m=window_value(risk, "12m", "max_drawdown"),
        sharpe_12m=window_value(risk, "12m", "sharpe", RATIO_DIGITS),
        peer_count=position["peer_count"] if position else 0,
        peer_return_percentile_12m=rounded(position["fund_return_percentile"], RATIO_DIGITS) if position else None,
        peer_volatility_percentile_12m=rounded(position["volatility_percentile"], RATIO_DIGITS) if position else None,
        issues=issue_counts(issues),
        open_issues=open_issue_counts(issues),
    )


def build_windows(windows: pl.DataFrame, benchmarks: list[str]) -> list[WindowRow]:
    market = [b for b in benchmarks if b != CDI]
    rows = {row["window"]: row for row in windows.iter_rows(named=True)}
    return [
        WindowRow(
            window=window,
            base_date=row["base_date"],
            end_date=row["end_date"],
            business_days=row["business_days"],
            fund_return=rounded(row["fund_return"], RETURN_DIGITS),
            fund_annualized=rounded(row["fund_annualized"], RETURN_DIGITS),
            cdi_return=rounded(row["cdi_return"], RETURN_DIGITS),
            cdi_annualized=rounded(row["cdi_annualized"], RETURN_DIGITS),
            pct_cdi=rounded(row["pct_cdi"], RATIO_DIGITS),
            benchmark_returns={b: rounded(row[f"{b}_return"], RETURN_DIGITS) for b in market},
            excess_returns={b: rounded(row[f"excess_{b}"], RETURN_DIGITS) for b in benchmarks},
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
            unexplained_share=rounded(row["unexplained_share"], RETURN_DIGITS),
        )
        for row in flows.sort("month").iter_rows(named=True)
    ]


def build_peer_position(position: dict | None) -> PeerPosition | None:
    if position is None or position["peer_count"] < MIN_PEERS:
        return None
    return PeerPosition(
        anbima_classification=position["anbima_classification"],
        target_audience=position["target_audience"],
        peer_count=position["peer_count"],
        metrics={
            metric: PeerMetric(
                value=rounded(position[metric], RETURN_DIGITS),
                percentile=rounded(position[f"{metric}_percentile"], RATIO_DIGITS),
                p25=rounded(position[f"{metric}_p25"], RETURN_DIGITS),
                median=rounded(position[f"{metric}_median"], RETURN_DIGITS),
                p75=rounded(position[f"{metric}_p75"], RETURN_DIGITS),
            )
            for metric in PEER_METRICS
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
            deviation=rounded(row["deviation"], RETURN_DIGITS),
            detail=row["detail"],
            status=row["status"],
            note=row["note"],
            treated_on=row["treated_on"],
        )
        for row in issues.iter_rows(named=True)
    ]


def build_events(issues: pl.DataFrame, names: dict[str, str]) -> list[QualityEvent]:
    reviewed = pl.col("status").filter(pl.col("severity") != INFO)
    common_status = (
        pl.when(reviewed.n_unique() == 1)
        .then(reviewed.first())
        .when((reviewed.len() == 0) & (pl.col("status").n_unique() == 1))
        .then(pl.col("status").first())
        .otherwise(pl.lit(OPEN))
    )
    common_note = pl.when(pl.col("note").n_unique() == 1).then(pl.col("note").first())
    events = (
        issues.filter(pl.col("rule") == EVENT_RULE, pl.col("series_id").is_not_null(), pl.col("date").is_not_null())
        .group_by("date")
        .agg(
            pl.col("series_id").unique().sort().alias("series_ids"),
            pl.col("severity").sort_by(severity_rank()).first().alias("severity"),
            common_status.alias("status"),
            common_note.alias("note"),
            pl.col("series_id").str.split("-").list.first().n_unique().alias("cnpj_count"),
        )
        .filter(pl.col("series_ids").list.len() >= EVENT_MIN_SERIES)
        .sort("date", descending=True)
    )
    return [
        QualityEvent(
            rule=EVENT_RULE,
            date=row["date"],
            severity=row["severity"],
            status=row["status"],
            note=row["note"],
            series_ids=row["series_ids"],
            display_names=[names.get(key, key) for key in row["series_ids"]],
            cnpj_count=row["cnpj_count"],
        )
        for row in events.iter_rows(named=True)
    ]


def quality_summary(issues: pl.DataFrame, metrics: dict[str, pl.DataFrame]) -> QualitySummary:
    coverage = metrics[COVERAGE_METRIC].row(0, named=True)
    return QualitySummary(
        checked_series=coverage["checked_series"],
        checked_days=coverage["checked_days"],
        by_severity=issue_counts(issues).model_dump(),
        by_rule=dict(issues.group_by("rule").len().sort("rule").iter_rows()) if issues.height else {},
        open_by_severity={severity: count for severity, count in open_issue_counts(issues).model_dump().items() if severity in OPEN_SEVERITIES},
        by_status={status: issues.filter(pl.col("status") == status).height for status in STATUSES},
        treated=issues.filter(pl.col("status") != OPEN).height,
    )


def write_json(path: Path, document: Contract | list[Contract]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(document, list):
        payload = json.dumps([item.model_dump(mode="json") for item in document], ensure_ascii=False, separators=(",", ":"))
    else:
        payload = document.model_dump_json()
    path.write_text(payload, encoding="utf-8")


def verify_site(directory: Path) -> None:
    meta = Meta.model_validate_json((directory / "meta.json").read_text(encoding="utf-8"))
    funds = TypeAdapter(list[FundSummary]).validate_json((directory / "funds.json").read_text(encoding="utf-8"))
    Aggregates.model_validate_json((directory / "aggregates.json").read_text(encoding="utf-8"))
    quality = QualityDocument.model_validate_json((directory / "quality.json").read_text(encoding="utf-8"))
    details = sorted((directory / FUNDS_DIRECTORY).glob("*.json"))
    if not meta.universe.monitored_series == len(funds) == len(details):
        raise ValueError(f"site: {meta.universe.monitored_series} monitored series, {len(funds)} summaries, {len(details)} fund files")
    if sum(quality.summary.by_severity.values()) != len(quality.issues):
        raise ValueError(f"site: quality summary counts {sum(quality.summary.by_severity.values())} issues, list has {len(quality.issues)}")
    if sum(quality.summary.by_status.values()) != len(quality.issues):
        raise ValueError(f"site: quality status counts {sum(quality.summary.by_status.values())} issues, list has {len(quality.issues)}")
    if quality.summary.treated != len(quality.issues) - quality.summary.by_status[OPEN]:
        raise ValueError(f"site: {quality.summary.treated} treated issues, status counts say {len(quality.issues) - quality.summary.by_status[OPEN]}")
    open_listed = sum(1 for issue in quality.issues if issue.status == OPEN and issue.severity in OPEN_SEVERITIES)
    if sum(quality.summary.open_by_severity.values()) != open_listed:
        raise ValueError(f"site: quality summary counts {sum(quality.summary.open_by_severity.values())} open issues, list has {open_listed}")
    if meta.quality != quality.summary:
        raise ValueError("site: meta and quality.json disagree on the quality summary")
    for path in details:
        detail = FundDetail.model_validate_json(path.read_text(encoding="utf-8"))
        if detail.summary.series_id != path.stem:
            raise ValueError(f"site: {path.name} holds series {detail.summary.series_id}")
        if any(len(values) != len(detail.cumulative.dates) for values in detail.cumulative.values.values()):
            raise ValueError(f"site: {path.name} has cumulative series of different lengths")


def publish_site(registry: pl.DataFrame, reference_date: date) -> None:
    metrics = load_metrics()
    attributes = fund_attributes(registry)
    names = dict(attributes.select("series_id", "display_name").iter_rows())
    windows = by_series(metrics["window_returns"])
    risks = by_series(metrics["risk"])
    cumulative = by_series(metrics["cumulative_index"])
    drawdowns = by_series(metrics["drawdown"])
    monthly = by_series(metrics["monthly_flows"])
    flows = {row["series_id"]: row for row in metrics["flow_summary"].iter_rows(named=True)}
    positions = {row["series_id"]: row for row in metrics["peer_positions"].iter_rows(named=True)}
    issues = apply_triage(metrics[ISSUES_METRIC], load_triage(config.TRIAGE_FILE))
    issues_by_series = by_series(issues.filter(pl.col("series_id").is_not_null()))
    empty = {name: frame.clear() for name, frame in metrics.items()} | {ISSUES_METRIC: issues.clear()}

    summaries, details = [], {}
    for attribute in attributes.iter_rows(named=True):
        key = attribute["series_id"]
        fund_windows = windows.get(key, empty["window_returns"])
        fund_risk = risks.get(key, empty["risk"])
        fund_cumulative = cumulative.get(key, empty["cumulative_index"])
        fund_issues = issues_by_series.get(key, empty[ISSUES_METRIC])
        summary = build_summary(attribute, fund_windows, fund_risk, flows.get(key), positions.get(key), fund_issues)
        benchmarks = summary.benchmarks
        summaries.append(summary)
        details[key] = FundDetail(
            summary=summary,
            windows=build_windows(fund_windows, benchmarks),
            risk=build_risk(fund_risk, summary.market_benchmark),
            cumulative=build_series(
                fund_cumulative, {"fund": "fund_index", **{b: f"{b}_index" for b in benchmarks}}, INDEX_DIGITS
            ),
            drawdown=build_series(drawdowns.get(key, empty["drawdown"]), {"fund": "drawdown"}, RETURN_DIGITS),
            monthly_flows=build_flows(monthly.get(key, empty["monthly_flows"])),
            peers=build_peer_position(positions.get(key)),
            issues=build_issues(fund_issues, names),
        )

    manager = select_manager_series(registry, config.MANAGER_CNPJ)
    manager_names = manager["manager_names"].explode(empty_as_null=True)
    manager_cnpjs = manager["manager_cnpjs"].explode(empty_as_null=True)
    quality = quality_summary(issues, metrics)
    source_dates = metrics[SOURCES_METRIC].row(0, named=True)
    meta = Meta(
        generated_at=datetime.now(timezone.utc),
        reference_date=reference_date,
        as_of=metrics["window_returns"]["end_date"].max(),
        window_start=config.WINDOW_START,
        manager_cnpj=config.MANAGER_CNPJ,
        manager_name=manager_names.filter(manager_cnpjs == config.MANAGER_CNPJ).first(),
        universe=UniverseCounts(
            manager_series=manager.height,
            exclusive_series=manager.filter(pl.col("exclusive")).height,
            monitored_series=attributes.height,
            general_public_series=attributes.filter(pl.col("target_audience") == GENERAL_PUBLIC).height,
            peer_candidates=select_peer_universe(registry, config.MANAGER_CNPJ).height,
            peer_eligible=metrics["peers"]["eligible"].sum(),
        ),
        sources=[SourceStatus(source=source, last_date=last_date) for source, last_date in source_dates.items()],
        quality=quality,
        windows=list(WINDOWS),
    )
    aggregates = Aggregates(
        totals=[
            AggregateTotal(
                **{
                    **row,
                    "net_assets": rounded(row["net_assets"], MONEY_DIGITS),
                    "net_flow_12m": rounded(row["net_flow_12m"], MONEY_DIGITS),
                }
            )
            for row in metrics["aggregate_totals"].iter_rows(named=True)
        ],
        monthly=[
            AggregateRow(
                **{
                    **row,
                    "net_flow": rounded(row["net_flow"], MONEY_DIGITS),
                    "net_assets_end": rounded(row["net_assets_end"], MONEY_DIGITS),
                }
            )
            for row in metrics["aggregate_monthly"].iter_rows(named=True)
        ],
    )

    if config.SITE_DIR.exists():
        shutil.rmtree(config.SITE_DIR)
    write_json(config.SITE_DIR / "meta.json", meta)
    write_json(config.SITE_DIR / "funds.json", summaries)
    write_json(config.SITE_DIR / "aggregates.json", aggregates)
    write_json(
        config.SITE_DIR / "quality.json",
        QualityDocument(summary=quality, issues=build_issues(issues, names), events=build_events(issues, names)),
    )
    for key, detail in details.items():
        write_json(config.SITE_DIR / FUNDS_DIRECTORY / f"{key}.json", detail)
    verify_site(config.SITE_DIR)
    logger.info(
        "site: %d funds, %d issues (%d treated, %d open) written to %s",
        len(summaries),
        issues.height,
        quality.treated,
        sum(quality.open_by_severity.values()),
        config.SITE_DIR,
    )
