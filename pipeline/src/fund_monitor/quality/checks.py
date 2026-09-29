from dataclasses import dataclass
from datetime import date, timedelta

import polars as pl

from fund_monitor.calc.peers import PEER_WINDOW
from fund_monitor.calc.series import SERIES_KEY, series_id, split_dates, subclassed_cnpjs

HIGH = "high"
MEDIUM = "medium"
LOW = "low"
INFO = "info"
SEVERITIES = (HIGH, MEDIUM, LOW, INFO)

ISSUE_SCHEMA = {
    "rule": pl.String,
    "severity": pl.String,
    "series_id": pl.String,
    "date": pl.Date,
    "end_date": pl.Date,
    "days": pl.Int64,
    "value": pl.Float64,
    "threshold": pl.Float64,
    "detail": pl.String,
}

LONG_GAP_DAYS = 5
JUMP_LOOKBACK = 60
JUMP_SIGMAS = 5.0
MATERIAL_DEVIATION = 0.001
MARKET_JUMP_SHARE = 0.10
FIXED_INCOME_JUMP = 0.03
FIXED_INCOME = "Renda Fixa"
REPEATED_QUOTA_DAYS = 3
UNEXPLAINED_SHARE = 0.01
SOURCE_TOLERANCE_WEEKDAYS = {"cvm_daily": 2, "cdi": 1, "ima_b": 1, "ibov": 1, "ibrx": 1}
SOURCE_HIGH_EXTRA_WEEKDAYS = 3


@dataclass(frozen=True)
class QualityInputs:
    raw_daily: pl.DataFrame
    daily: pl.DataFrame
    manager_series: pl.DataFrame
    manager_registry: pl.DataFrame
    monitored: pl.DataFrame
    quotas: pl.DataFrame
    returns: pl.DataFrame
    monthly_flows: pl.DataFrame
    windows: pl.DataFrame
    calendar: list[date]
    market_jump_share: pl.DataFrame
    source_dates: dict[str, date | None]
    as_of: date
    reference_date: date


def issues(frame: pl.DataFrame, rule: str, severity: str | pl.Expr, **columns: pl.Expr) -> pl.DataFrame:
    severity_expr = pl.lit(severity) if isinstance(severity, str) else severity
    defaults = {name: pl.lit(None, dtype=dtype) for name, dtype in ISSUE_SCHEMA.items()}
    selected = {**defaults, **columns, "rule": pl.lit(rule), "severity": severity_expr}
    return frame.select(selected[name].cast(dtype).alias(name) for name, dtype in ISSUE_SCHEMA.items())


def attach_series(rows: pl.DataFrame, monitored: pl.DataFrame, quotas: pl.DataFrame) -> pl.DataFrame:
    keys = monitored.select(SERIES_KEY).unique().with_columns(series_id())
    exact = rows.join(keys, on=SERIES_KEY, nulls_equal=True)
    handoffs = (
        quotas.group_by("series_id")
        .agg(pl.col("date").filter(pl.col("inherited").not_()).min().alias("first_own_date"), pl.col("inherited").any().alias("inherits"))
        .filter("inherits")
    )
    heirs = keys.filter(pl.col("subclass_id").is_not_null()).select("cnpj", "series_id").join(handoffs, on="series_id")
    inherited = (
        rows.filter(pl.col("subclass_id").is_null())
        .join(heirs, on="cnpj")
        .filter(pl.col("date") < pl.col("first_own_date"))
    )
    return pl.concat([exact, inherited.select(exact.columns)])


def consecutive_run(position: str) -> pl.Expr:
    return (pl.col(position) - pl.int_range(pl.len()).over("series_id")).alias("run")


def expected_reports(inputs: QualityInputs) -> pl.DataFrame:
    calendar = pl.DataFrame({"date": inputs.calendar}).filter(pl.col("date") <= inputs.as_of).with_row_index("position")
    spans = inputs.quotas.group_by("series_id").agg(pl.col("date").min().alias("first_date"))
    return spans.join(calendar, how="cross").filter(pl.col("date") >= pl.col("first_date"))


def missing_reports(inputs: QualityInputs) -> pl.DataFrame:
    missing = (
        expected_reports(inputs).join(inputs.quotas.select("series_id", "date"), on=["series_id", "date"], how="anti")
        .sort("series_id", "position")
        .with_columns(consecutive_run("position"))
        .group_by("series_id", "run")
        .agg(pl.col("date").min().alias("start"), pl.col("date").max().alias("end"), pl.len().alias("days"))
    )
    severity = pl.when(pl.col("days") >= LONG_GAP_DAYS).then(pl.lit(MEDIUM)).otherwise(pl.lit(LOW))
    return issues(
        missing, "missing_report", severity, series_id=pl.col("series_id"), date=pl.col("start"), end_date=pl.col("end"), days=pl.col("days")
    )


def with_spanned_days(returns: pl.DataFrame, calendar: list[date]) -> pl.DataFrame:
    positions = pl.DataFrame({"date": calendar}, schema={"date": pl.Date}).with_row_index("position")
    position = pl.col("position").cast(pl.Int64)
    spanned = position - position.shift(1).over("series_id")
    return (
        returns.join(positions, on="date", how="left")
        .sort("series_id", "date")
        .with_columns(spanned.fill_null(1).clip(lower_bound=1).alias("spanned_days"))
        .drop("position")
    )


def flag_jumps(returns: pl.DataFrame, calendar: list[date]) -> pl.DataFrame:
    days = pl.col("spanned_days")
    daily_equivalent = (1 + pl.col("daily_return")) ** (1 / days) - 1
    flagged = with_spanned_days(returns, calendar).with_columns(
        daily_equivalent.rolling_mean(JUMP_LOOKBACK).shift(1).over("series_id").alias("prior_mean"),
        daily_equivalent.rolling_std(JUMP_LOOKBACK).shift(1).over("series_id").alias("prior_std"),
    )
    deviation = (pl.col("daily_return") - days * pl.col("prior_mean")).abs()
    statistical_limit = JUMP_SIGMAS * pl.col("prior_std") * days.sqrt()
    statistical = (deviation > statistical_limit) & (deviation >= MATERIAL_DEVIATION)
    absolute = (pl.col("cvm_classification") == FIXED_INCOME) & (pl.col("daily_return").abs() > FIXED_INCOME_JUMP)
    return flagged.with_columns(
        statistical.fill_null(False).alias("statistical_jump"),
        absolute.fill_null(False).alias("absolute_jump"),
        pl.max_horizontal(statistical_limit, pl.lit(MATERIAL_DEVIATION)).alias("statistical_threshold"),
    )


def market_jump_share(returns: pl.DataFrame, calendar: list[date]) -> pl.DataFrame:
    return (
        flag_jumps(returns, calendar)
        .filter(pl.col("prior_std").is_not_null())
        .group_by("date", "cvm_classification")
        .agg(pl.col("statistical_jump").mean().alias("market_share"))
    )


def quota_jumps(inputs: QualityInputs) -> pl.DataFrame:
    classification = inputs.monitored.with_columns(series_id()).select("series_id", "cvm_classification")
    jumps = (
        flag_jumps(inputs.returns.join(classification, on="series_id", how="left"), inputs.calendar)
        .filter(pl.col("statistical_jump") | pl.col("absolute_jump"))
        .join(inputs.market_jump_share, on=["date", "cvm_classification"], how="left")
    )
    market_day = pl.col("market_share").fill_null(0) >= MARKET_JUMP_SHARE
    kind = pl.when(pl.col("absolute_jump")).then(pl.lit("absolute")).otherwise(pl.lit("statistical"))
    threshold = pl.when(pl.col("absolute_jump")).then(pl.lit(FIXED_INCOME_JUMP)).otherwise(pl.col("statistical_threshold"))
    return issues(
        jumps,
        "quota_jump",
        pl.when(market_day).then(pl.lit(INFO)).otherwise(pl.lit(MEDIUM)),
        series_id=pl.col("series_id"),
        date=pl.col("date"),
        value=pl.col("daily_return"),
        threshold=threshold,
        detail=pl.concat_str(kind, pl.when(market_day).then(pl.lit("; market-wide")).otherwise(pl.lit(""))),
    )


def repeated_quotas(inputs: QualityInputs) -> pl.DataFrame:
    runs = (
        inputs.quotas.sort("series_id", "date")
        .with_columns(
            (pl.col("quota_value") != pl.col("quota_value").shift(1).over("series_id")).fill_null(True).cum_sum().over("series_id").alias("run")
        )
        .group_by("series_id", "run")
        .agg(pl.col("date").min().alias("start"), pl.col("date").max().alias("end"), pl.len().alias("days"), pl.col("quota_value").first())
        .filter(pl.col("days") >= REPEATED_QUOTA_DAYS)
    )
    return issues(
        runs,
        "repeated_quota",
        MEDIUM,
        series_id=pl.col("series_id"),
        date=pl.col("start"),
        end_date=pl.col("end"),
        days=pl.col("days"),
        value=pl.col("quota_value").cast(pl.Float64),
    )


def unexplained_net_assets(inputs: QualityInputs) -> pl.DataFrame:
    flagged = inputs.monthly_flows.filter(pl.col("unexplained_share").abs() > UNEXPLAINED_SHARE)
    return issues(
        flagged,
        "unexplained_net_assets",
        MEDIUM,
        series_id=pl.col("series_id"),
        date=pl.col("month"),
        end_date=pl.col("last_report_date"),
        value=pl.col("unexplained_share"),
        threshold=pl.lit(UNEXPLAINED_SHARE),
    )


def zero_values(inputs: QualityInputs) -> pl.DataFrame:
    invalid = {
        "quota": pl.col("quota_value") <= 0,
        "net_assets": pl.col("net_assets") <= 0,
        "shareholders": pl.col("shareholders") == 0,
    }
    rows = attach_series(inputs.daily, inputs.monitored, inputs.quotas).filter(pl.any_horizontal(invalid.values()))
    detail = pl.concat_str([pl.when(condition).then(pl.lit(name)) for name, condition in invalid.items()], separator=",", ignore_nulls=True)
    return issues(rows, "zero_values", HIGH, series_id=pl.col("series_id"), date=pl.col("date"), detail=detail)


def short_history(inputs: QualityInputs) -> pl.DataFrame:
    short = inputs.windows.filter(pl.col("window") == PEER_WINDOW, pl.col("fund_return").is_null())
    return issues(short, "short_history", INFO, series_id=pl.col("series_id"), date=pl.col("first_date"))


def duplicate_reports(inputs: QualityInputs) -> pl.DataFrame:
    value_columns = ["quota_value", "net_assets", "total_assets", "inflows", "outflows", "shareholders"]
    groups = (
        inputs.raw_daily.group_by(*SERIES_KEY, "date")
        .agg(
            pl.len().alias("rows"),
            pl.col("report_type").unique().sort().str.join(", ").alias("report_types"),
            *(pl.col(column).n_unique().alias(column) for column in value_columns),
        )
        .filter(pl.col("rows") > 1)
    )
    differing = pl.concat_str([pl.when(pl.col(c) > 1).then(pl.lit(c)) for c in value_columns], separator=",", ignore_nulls=True)
    conflicts = groups.with_columns(differing.alias("differing")).filter(pl.col("differing") != "")
    attached = attach_series(conflicts, inputs.monitored, inputs.quotas)
    return issues(
        attached,
        "duplicate_report",
        MEDIUM,
        series_id=pl.col("series_id"),
        date=pl.col("date"),
        days=pl.col("rows"),
        detail=pl.concat_str(pl.lit("types: "), pl.col("report_types"), pl.lit("; differing: "), pl.col("differing")),
    )


def weekday_lag(last: date | None, expected: date) -> int | None:
    if last is None:
        return None
    return sum(1 for offset in range(1, (expected - last).days + 1) if (last + timedelta(days=offset)).weekday() < 5)


def last_closed_weekday(reference_date: date) -> date:
    day = reference_date - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def stale_sources(inputs: QualityInputs) -> pl.DataFrame:
    expected = last_closed_weekday(inputs.reference_date)
    rows = []
    for source, tolerance in SOURCE_TOLERANCE_WEEKDAYS.items():
        last = inputs.source_dates.get(source)
        lag = weekday_lag(last, expected)
        if lag is None or lag > tolerance:
            severity = HIGH if lag is None or lag > tolerance + SOURCE_HIGH_EXTRA_WEEKDAYS else MEDIUM
            rows.append({"source": source, "last": last, "lag": lag, "tolerance": tolerance, "severity": severity})
    frame = pl.DataFrame(rows, schema={"source": pl.String, "last": pl.Date, "lag": pl.Int64, "tolerance": pl.Int64, "severity": pl.String})
    return issues(
        frame,
        "stale_source",
        pl.col("severity"),
        date=pl.col("last"),
        end_date=pl.lit(expected),
        days=pl.col("lag"),
        threshold=pl.col("tolerance").cast(pl.Float64),
        detail=pl.col("source"),
    )


def registry_mismatches(inputs: QualityInputs) -> pl.DataFrame:
    active = inputs.manager_series.select(SERIES_KEY).unique()
    registered = pl.concat([active, inputs.manager_registry.select(SERIES_KEY)]).unique()
    inherited = (
        pl.col("subclass_id").is_null()
        & pl.col("cnpj").is_in(subclassed_cnpjs(active)["cnpj"].to_list())
        & (pl.col("date") < pl.col("split_date")).fill_null(False)
    )
    seen = (
        inputs.raw_daily.join(split_dates(inputs.raw_daily), on="cnpj", how="left")
        .filter(inherited.not_())
        .group_by(SERIES_KEY)
        .agg(pl.col("date").min().alias("first"), pl.col("date").max().alias("last"), pl.len().alias("rows"))
    )
    unregistered = seen.join(registered, on=SERIES_KEY, how="anti", nulls_equal=True).with_columns(
        detail=pl.lit("reported but not registered")
    )
    inactive = (
        seen.join(registered, on=SERIES_KEY, how="semi", nulls_equal=True)
        .join(active, on=SERIES_KEY, how="anti", nulls_equal=True)
        .with_columns(detail=pl.lit("reported but not active"))
    )
    unreported = inputs.monitored.select(SERIES_KEY).join(seen, on=SERIES_KEY, how="anti", nulls_equal=True).with_columns(series_id())
    return pl.concat(
        [
            issues(
                pl.concat([unregistered, inactive]).with_columns(series_id()),
                "registry_mismatch",
                MEDIUM,
                series_id=pl.col("series_id"),
                date=pl.col("first"),
                end_date=pl.col("last"),
                days=pl.col("rows"),
                detail=pl.col("detail"),
            ),
            issues(unreported, "registry_mismatch", MEDIUM, series_id=pl.col("series_id"), detail=pl.lit("registered but never reported")),
        ]
    )


RULES = (
    missing_reports,
    quota_jumps,
    repeated_quotas,
    unexplained_net_assets,
    zero_values,
    short_history,
    duplicate_reports,
    stale_sources,
    registry_mismatches,
)


RULE_NAMES = (
    "missing_report",
    "quota_jump",
    "repeated_quota",
    "unexplained_net_assets",
    "zero_values",
    "short_history",
    "duplicate_report",
    "stale_source",
    "registry_mismatch",
)


def run_checks(inputs: QualityInputs) -> pl.DataFrame:
    severity_rank = pl.col("severity").replace_strict({s: rank for rank, s in enumerate(SEVERITIES)}, return_dtype=pl.Int8)
    return pl.concat([rule(inputs) for rule in RULES]).sort(severity_rank, "rule", "series_id", "date", nulls_last=True)


def checked_days(inputs: QualityInputs) -> int:
    return expected_reports(inputs).height
