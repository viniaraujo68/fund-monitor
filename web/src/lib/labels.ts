export const BENCHMARK_LABELS: Record<string, string> = {
  cdi: "CDI",
  ima_b: "IMA-B",
  ibov: "Ibovespa",
  ibrx: "IBrX-100",
};

export const WINDOW_LABELS: Record<string, string> = {
  mtd: "No mês",
  ytd: "No ano",
  "3m": "3 meses",
  "6m": "6 meses",
  "12m": "12 meses",
  "24m": "24 meses",
  since_start: "Desde o início",
};

export const SEVERITIES = ["high", "medium", "low", "info"] as const;

export type Severity = (typeof SEVERITIES)[number];

export const SEVERITY_LABELS: Record<Severity, string> = {
  high: "Alta",
  medium: "Média",
  low: "Baixa",
  info: "Informativo",
};

export const SEVERITY_BADGE_CLASS: Record<Severity, string> = {
  high: "badge-error",
  medium: "badge-warning",
  low: "",
  info: "",
};

const SEVERITY_COUNT_WORDS: Record<Severity, [string, string]> = {
  high: ["alta", "altas"],
  medium: ["média", "médias"],
  low: ["baixa", "baixas"],
  info: ["informativo", "informativos"],
};

export const SOURCE_LABELS: Record<string, string> = {
  cvm_daily: "Informe diário CVM",
  cdi: "CDI (Bacen)",
  ima_b: "IMA-B (ANBIMA)",
  ibov: "Ibovespa (B3)",
  ibrx: "IBrX-100 (B3)",
};

export const CLASSIFICATIONS = ["Renda Fixa", "Multimercado", "Ações"] as const;

export const GENERAL_PUBLIC = "Público Geral";

export const AUDIENCES = [GENERAL_PUBLIC, "Qualificado", "Profissional"] as const;

export const ALL = "all";

const lookup = (labels: Record<string, string>, key: string): string => labels[key] ?? key;

export const benchmarkLabel = (key: string): string => lookup(BENCHMARK_LABELS, key);

const listFormat = new Intl.ListFormat("pt-BR", { style: "long", type: "conjunction" });

export const benchmarkList = (keys: string[]): string => listFormat.format(keys.map(benchmarkLabel));

export const windowLabel = (key: string): string => lookup(WINDOW_LABELS, key);

export const sourceLabel = (key: string): string => lookup(SOURCE_LABELS, key);

export const isSeverity = (value: string): value is Severity =>
  (SEVERITIES as readonly string[]).includes(value);

export const severityRank = (key: string): number =>
  isSeverity(key) ? SEVERITIES.indexOf(key) : SEVERITIES.length;

export const severityLabel = (key: string): string =>
  isSeverity(key) ? SEVERITY_LABELS[key] : key;

export const severityBadgeClass = (key: string): string =>
  isSeverity(key) ? SEVERITY_BADGE_CLASS[key] : "";

export const severityCountWord = (key: Severity, count: number): string =>
  SEVERITY_COUNT_WORDS[key][count === 1 ? 0 : 1];

export const STATUSES = ["open", "explained", "source_error", "limitation"] as const;

export type Status = (typeof STATUSES)[number];

export const TREATED_STATUSES = ["explained", "source_error", "limitation"] as const;

export const STATUS_LABELS: Record<Status, string> = {
  open: "Aberto",
  explained: "Explicado",
  source_error: "Erro da fonte",
  limitation: "Limitação do informe",
};

export const OPEN_SEVERITIES = ["high", "medium", "low"] as const;

export const isStatus = (value: string): value is Status =>
  (STATUSES as readonly string[]).includes(value);

export const statusLabel = (key: string): string => (isStatus(key) ? STATUS_LABELS[key] : key);

export const countsAsOpen = (status: string, severity: string): boolean =>
  status === "open" && severity !== "info";

export const untreatedInfo = (status: string, severity: string): boolean =>
  status === "open" && severity === "info";
