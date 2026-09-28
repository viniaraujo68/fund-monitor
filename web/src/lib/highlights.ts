import type { FundSummary, IsoDate, Issue, Meta, QualityDocument } from "$lib/data/types";
import { GENERAL_PUBLIC } from "$lib/labels";

const LEADER_LIMIT = 6;
const FLOW_LIMIT = 5;
const EVENT_MIN_CNPJS = 3;
const EVENT_RULE = "quota_jump";
const EVENT_SEVERITY = "medium";
const MARKET_WIDE_MARK = "market-wide";
const INCENTIVIZED_PATTERN = /incentivad/i;

export interface HighlightFund {
  seriesId: string;
  name: string;
  linked: boolean;
}

export interface CdiLeader extends HighlightFund {
  pctCdi: number;
  return12m: number | null;
}

export interface CdiHighlight {
  beating: number;
  measured: number;
  cdi12m: number | null;
  leaders: CdiLeader[];
  hiddenLeaders: number;
}

export interface FlowBar extends HighlightFund {
  netFlow: number;
  partial: boolean;
}

export interface FlowHighlight {
  bars: FlowBar[];
  hasPartial: boolean;
}

export interface EventSeries extends HighlightFund {
  change: number | null;
}

export interface CreditEvent {
  date: IsoDate;
  windowStart: IsoDate;
  cnpjCount: number;
  series: EventSeries[];
  minChange: number | null;
  maxChange: number | null;
}

export interface IncentivizedFund extends HighlightFund {
  return12m: number;
  peerPercentile: number | null;
  peerCount: number;
}

export interface Highlights {
  asOf: IsoDate;
  cdi: CdiHighlight | null;
  inflows: FlowHighlight | null;
  outflows: FlowHighlight | null;
  creditEvent: CreditEvent | null;
  incentivized: IncentivizedFund[] | null;
}

const fundRef = (fund: FundSummary): HighlightFund => ({
  seriesId: fund.series_id,
  name: fund.display_name,
  linked: true,
});

const isHighlightUniverse = (fund: FundSummary): boolean =>
  fund.target_audience === GENERAL_PUBLIC && !fund.structural_vehicle;

const windowCdi = (funds: FundSummary[], asOf: IsoDate): number | null =>
  funds.find((fund) => fund.last_date === asOf && fund.cdi_12m !== null)?.cdi_12m ?? null;

const buildCdi = (universe: FundSummary[], cdi12m: number | null): CdiHighlight | null => {
  const measured = universe.filter((fund) => fund.pct_cdi_12m !== null);
  if (measured.length === 0) return null;
  const beating = measured
    .filter((fund) => (fund.pct_cdi_12m ?? 0) > 1)
    .sort((a, b) => (b.pct_cdi_12m ?? 0) - (a.pct_cdi_12m ?? 0));
  return {
    beating: beating.length,
    measured: measured.length,
    cdi12m,
    leaders: beating.slice(0, LEADER_LIMIT).map((fund) => ({
      ...fundRef(fund),
      pctCdi: fund.pct_cdi_12m ?? 0,
      return12m: fund.return_12m,
    })),
    hiddenLeaders: Math.max(0, beating.length - LEADER_LIMIT),
  };
};

const buildFlows = (universe: FundSummary[], direction: 1 | -1): FlowHighlight | null => {
  const bars = universe
    .filter((fund) => fund.net_flow_12m !== null && fund.net_flow_12m * direction > 0)
    .sort((a, b) => ((b.net_flow_12m ?? 0) - (a.net_flow_12m ?? 0)) * direction)
    .slice(0, FLOW_LIMIT)
    .map((fund) => ({
      ...fundRef(fund),
      netFlow: fund.net_flow_12m ?? 0,
      partial: fund.flow_window_partial === true,
    }));
  if (bars.length === 0) return null;
  return { bars, hasPartial: bars.some((bar) => bar.partial) };
};

type IsolatedDrop = Issue & { date: IsoDate; series_id: string; value: number };

const isIsolatedDrop = (issue: Issue): issue is IsolatedDrop =>
  issue.rule === EVENT_RULE &&
  issue.severity === EVENT_SEVERITY &&
  issue.date !== null &&
  issue.series_id !== null &&
  issue.value !== null &&
  issue.value < 0 &&
  !(issue.detail ?? "").includes(MARKET_WIDE_MARK);

const classCnpj = (seriesId: string): string => seriesId.split("-")[0] ?? seriesId;

const distinctCnpjs = (drops: Map<string, IsolatedDrop>): number =>
  new Set([...drops.keys()].map(classCnpj)).size;

const totalDrop = (drops: Map<string, IsolatedDrop>): number =>
  [...drops.values()].reduce((sum, issue) => sum + Math.abs(issue.value), 0);

const buildCreditEvent = (
  funds: FundSummary[],
  quality: QualityDocument,
  windowStart: IsoDate,
  asOf: IsoDate,
): CreditEvent | null => {
  const byDay = new Map<IsoDate, Map<string, IsolatedDrop>>();
  for (const issue of quality.issues.filter(isIsolatedDrop)) {
    if (issue.date < windowStart || issue.date > asOf) continue;
    const series = byDay.get(issue.date) ?? new Map<string, IsolatedDrop>();
    if (!series.has(issue.series_id)) series.set(issue.series_id, issue);
    byDay.set(issue.date, series);
  }

  const busiest = [...byDay.entries()]
    .filter(([, drops]) => distinctCnpjs(drops) >= EVENT_MIN_CNPJS)
    .sort(
      ([dayA, a], [dayB, b]) =>
        b.size - a.size || totalDrop(b) - totalDrop(a) || dayB.localeCompare(dayA),
    )[0];
  if (busiest === undefined) return null;

  const names = new Map(funds.map((fund) => [fund.series_id, fund.display_name]));
  const series = [...busiest[1].values()]
    .map((issue) => {
      const known = names.get(issue.series_id);
      return {
        seriesId: issue.series_id,
        name: known ?? issue.display_name ?? issue.series_id,
        linked: known !== undefined,
        change: issue.value,
      };
    })
    .sort((a, b) => (a.change ?? 0) - (b.change ?? 0) || a.name.localeCompare(b.name, "pt-BR"));

  const changes = series.flatMap((entry) => (entry.change === null ? [] : [entry.change]));
  return {
    date: busiest[0],
    windowStart,
    cnpjCount: distinctCnpjs(busiest[1]),
    series,
    minChange: changes.length === 0 ? null : Math.min(...changes),
    maxChange: changes.length === 0 ? null : Math.max(...changes),
  };
};

const buildIncentivized = (universe: FundSummary[]): IncentivizedFund[] | null => {
  const rows = universe
    .filter((fund) => INCENTIVIZED_PATTERN.test(fund.display_name) && fund.return_12m !== null)
    .sort((a, b) => a.display_name.localeCompare(b.display_name, "pt-BR"))
    .map((fund) => ({
      ...fundRef(fund),
      return12m: fund.return_12m ?? 0,
      peerPercentile: fund.peer_return_percentile_12m,
      peerCount: fund.peer_count,
    }));
  return rows.length === 0 ? null : rows;
};

export const buildHighlights = (
  funds: FundSummary[],
  quality: QualityDocument,
  meta: Meta,
): Highlights => {
  const universe = funds.filter(isHighlightUniverse);
  return {
    asOf: meta.as_of,
    cdi: buildCdi(universe, windowCdi(funds, meta.as_of)),
    inflows: buildFlows(universe, 1),
    outflows: buildFlows(universe, -1),
    creditEvent: buildCreditEvent(funds, quality, meta.window_start, meta.as_of),
    incentivized: buildIncentivized(universe),
  };
};
