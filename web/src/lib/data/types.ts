export type IsoDate = string;
export type IsoDateTime = string;

export interface SourceStatus {
  source: string;
  last_date: IsoDate | null;
}

export interface QualitySummary {
  checked_series: number;
  checked_days: number;
  by_severity: Record<string, number>;
  by_rule: Record<string, number>;
}

export interface UniverseCounts {
  manager_series: number;
  exclusive_series: number;
  monitored_series: number;
  general_public_series: number;
  peer_candidates: number;
  peer_eligible: number;
}

export interface Meta {
  generated_at: IsoDateTime;
  reference_date: IsoDate;
  as_of: IsoDate;
  window_start: IsoDate;
  manager_cnpj: string;
  manager_name: string;
  universe: UniverseCounts;
  sources: SourceStatus[];
  quality: QualitySummary;
  windows: string[];
}

export interface IssueCounts {
  high: number;
  medium: number;
  low: number;
  info: number;
}

export interface FundSummary {
  series_id: string;
  cnpj: string;
  subclass_id: string | null;
  display_name: string;
  class_name: string;
  subclass_name: string | null;
  cvm_classification: string | null;
  anbima_classification: string | null;
  target_audience: string | null;
  condominium: string | null;
  performance_benchmark: string | null;
  structural_vehicle: boolean;
  benchmarks: string[];
  market_benchmark: string | null;
  first_date: IsoDate | null;
  last_date: IsoDate | null;
  inherited_until: IsoDate | null;
  net_assets: number | null;
  shareholders: number | null;
  net_flow_12m: number | null;
  flow_window_partial: boolean | null;
  return_mtd: number | null;
  return_ytd: number | null;
  return_12m: number | null;
  return_24m: number | null;
  cdi_12m: number | null;
  pct_cdi_12m: number | null;
  volatility_12m: number | null;
  max_drawdown_12m: number | null;
  sharpe_12m: number | null;
  peer_count: number;
  peer_return_percentile_12m: number | null;
  issues: IssueCounts;
}

export interface WindowRow {
  window: string;
  base_date: IsoDate | null;
  end_date: IsoDate | null;
  business_days: number | null;
  fund_return: number | null;
  fund_annualized: number | null;
  cdi_return: number | null;
  cdi_annualized: number | null;
  pct_cdi: number | null;
  benchmark_returns: Record<string, number | null>;
}

export interface RiskRow {
  window: string;
  observations: number;
  volatility: number | null;
  sharpe: number | null;
  max_drawdown: number | null;
  peak_date: IsoDate | null;
  trough_date: IsoDate | null;
  recovery_date: IsoDate | null;
  positive_days_share: number | null;
  best_day: number | null;
  best_day_date: IsoDate | null;
  worst_day: number | null;
  worst_day_date: IsoDate | null;
  beta: number | null;
  tracking_error: number | null;
}

export interface Series {
  dates: IsoDate[];
  values: Record<string, (number | null)[]>;
}

export interface RollingRow {
  month: IsoDate;
  end_date: IsoDate;
  fund_return: number | null;
  cdi_return: number | null;
}

export interface FlowRow {
  month: IsoDate;
  net_flow: number | null;
  inflows: number | null;
  outflows: number | null;
  net_assets_end: number | null;
  shareholders_end: number | null;
  monthly_return: number | null;
  unexplained_share: number | null;
}

export interface PeerMetric {
  value: number | null;
  percentile: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
}

export interface PeerPosition {
  anbima_classification: string;
  target_audience: string;
  peer_count: number;
  metrics: Record<string, PeerMetric>;
}

export interface Issue {
  rule: string;
  severity: string;
  series_id: string | null;
  display_name: string | null;
  date: IsoDate | null;
  end_date: IsoDate | null;
  days: number | null;
  value: number | null;
  threshold: number | null;
  detail: string | null;
}

export interface FundDetail {
  summary: FundSummary;
  windows: WindowRow[];
  risk: RiskRow[];
  cumulative: Series;
  drawdown: Series;
  rolling_12m: RollingRow[];
  monthly_flows: FlowRow[];
  peers: PeerPosition | null;
  issues: Issue[];
}

export interface AggregateRow {
  scope: string;
  group: string;
  group_value: string | null;
  month: IsoDate;
  net_flow: number;
  net_assets_end: number;
  classes: number;
}

export interface AggregateTotal {
  scope: string;
  as_of: IsoDate;
  net_assets: number;
  net_flow_12m: number;
  classes: number;
}

export interface Aggregates {
  totals: AggregateTotal[];
  monthly: AggregateRow[];
}

export interface QualityDocument {
  summary: QualitySummary;
  issues: Issue[];
}
