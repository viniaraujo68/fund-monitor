import type { Issue } from "$lib/data/types";
import { date, integer, monthName, percent2, percentShort } from "$lib/format";
import { sourceLabel } from "$lib/labels";

export const RULE_LABELS: Record<string, string> = {
  zero_values: "Valores zerados",
  duplicate_report: "Informe duplicado",
  quota_jump: "Salto de cota",
  unexplained_net_assets: "PL sem explicação",
  missing_report: "Dia sem informe",
  short_history: "Histórico curto",
  repeated_quota: "Cota repetida",
  stale_source: "Fonte atrasada",
  registry_mismatch: "Cadastro divergente",
};

export const RULES = Object.keys(RULE_LABELS);

export const ruleLabel = (rule: string): string => RULE_LABELS[rule] ?? rule;

export interface RuleDescription {
  detects: string;
  threshold: string;
  severity: string;
}

export const RULE_DESCRIPTIONS: Record<string, RuleDescription> = {
  zero_values: {
    detects: "Informe publicado com cota, PL ou número de cotistas zerado.",
    threshold: "cota ≤ 0, PL ≤ 0 ou nenhum cotista",
    severity: "Alta",
  },
  duplicate_report: {
    detects: "Mais de um informe da mesma série no mesmo dia, com valores diferentes.",
    threshold: "2 ou mais informes no dia com algum valor divergente",
    severity: "Média",
  },
  quota_jump: {
    detects: "Variação diária da cota fora do padrão recente da série.",
    threshold: "5σ em 60 dias e ≥ 0,1 % da cota; 3 % absoluto em RF",
    severity: "Média; informativo quando ≥ 10 % da classe salta no mesmo dia",
  },
  unexplained_net_assets: {
    detects: "Variação mensal do PL que captação líquida e rentabilidade não explicam.",
    threshold: "resíduo > 1 % do PL do início do mês",
    severity: "Média",
  },
  missing_report: {
    detects: "Dia útil sem informe depois do início da série.",
    threshold: "qualquer dia útil sem informe",
    severity: "Baixa; média a partir de 5 dias úteis seguidos",
  },
  short_history: {
    detects: "Série com menos de 12 meses, fora de rankings e pares.",
    threshold: "sem retorno na janela de 12 meses",
    severity: "Informativo",
  },
  repeated_quota: {
    detects: "Mesma cota em informes seguidos, sinal de cota não atualizada.",
    threshold: "3 ou mais informes seguidos",
    severity: "Média",
  },
  stale_source: {
    detects: "Fonte de dados sem atualização recente.",
    threshold: "atraso > 2 dias úteis no informe CVM, > 1 nos índices",
    severity: "Média; alta com 3 dias úteis além da tolerância ou sem dado",
  },
  registry_mismatch: {
    detects: "Série no cadastro sem informe, ou informe de série fora do cadastro.",
    threshold: "qualquer divergência",
    severity: "Média",
  },
};

const FIELD_WORDS: Record<string, string> = {
  quota: "cota",
  quota_value: "cota",
  net_assets: "PL",
  total_assets: "patrimônio total",
  inflows: "aplicações",
  outflows: "resgates",
  shareholders: "cotistas",
};

const ZERO_AGREEMENT: Record<string, string> = {
  quota: "zerada",
  net_assets: "zerado",
  shareholders: "zerados",
};

const COUNT_WORDS = ["", "Um", "Dois", "Três", "Quatro", "Cinco"];

const listFormat = new Intl.ListFormat("pt-BR", { style: "long", type: "conjunction" });

const capitalize = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);

const fieldList = (fields: string[]): string =>
  listFormat.format(fields.map((field) => FIELD_WORDS[field] ?? field));

const splitFields = (detail: string | null): string[] =>
  (detail ?? "")
    .split(",")
    .map((field) => field.trim())
    .filter((field) => field !== "");

const plural = (count: number, singular: string, pluralForm: string): string =>
  `${integer(count)} ${count === 1 ? singular : pluralForm}`;

const businessDays = (count: number): string => plural(count, "dia útil", "dias úteis");

const detailPart = (detail: string | null, prefix: string): string | null => {
  const part = (detail ?? "")
    .split(";")
    .map((piece) => piece.trim())
    .find((piece) => piece.startsWith(prefix));
  return part === undefined ? null : part.slice(prefix.length).trim();
};

const zeroValues = (issue: Issue): string => {
  const fields = splitFields(issue.detail);
  const agreement =
    fields.length === 1 ? (ZERO_AGREEMENT[fields[0] ?? ""] ?? "zerado") : "zerados";
  const subject = fields.length === 0 ? "Valores" : capitalize(fieldList(fields));
  return `${subject} ${agreement} em ${date(issue.date)} com informe publicado.`;
};

const duplicateReport = (issue: Issue): string => {
  const count = issue.days ?? 2;
  const countWord = COUNT_WORDS[count] ?? integer(count);
  const types = (detailPart(issue.detail, "types:") ?? "")
    .split(", ")
    .filter((type) => type !== "");
  const differing = splitFields(detailPart(issue.detail, "differing:"));
  const typesPart = types.length === 0 ? "" : ` (${listFormat.format(types)})`;
  const differingPart =
    differing.length === 0 ? " com valores diferentes" : ` com ${fieldList(differing)} diferentes`;
  return `${countWord} informes em ${date(issue.date)}${typesPart}${differingPart}.`;
};

const quotaJump = (issue: Issue): string => {
  const flags = (issue.detail ?? "").split(";").map((flag) => flag.trim());
  const limit = flags.includes("absolute")
    ? `acima do limite de ${percentShort(0.03)} para renda fixa`
    : `desvio da média de 60 dias acima de ${percentShort(issue.threshold)} (5 desvios-padrão)`;
  const market = flags.includes("market-wide") ? "; movimento compartilhado pelo mercado" : "";
  return `Variação de ${percent2(issue.value)} na cota em ${date(issue.date)}, ${limit}${market}.`;
};

const unexplainedNetAssets = (issue: Issue): string => {
  const month = issue.date === null ? "no mês" : `Em ${monthName(issue.date)}`;
  const magnitude = issue.value === null ? null : Math.abs(issue.value);
  return `${capitalize(month)} o PL variou ${percent2(magnitude)} além do que captação e rentabilidade explicam (limite ${percentShort(issue.threshold)}).`;
};

const missingReport = (issue: Issue): string => {
  const days = issue.days ?? 1;
  const single = issue.end_date === null || issue.end_date === issue.date;
  const span = single
    ? `em ${date(issue.date)}`
    : `de ${date(issue.date)} a ${date(issue.end_date)}`;
  return `Sem informe ${span} (${businessDays(days)}).`;
};

const shortHistory = (issue: Issue): string =>
  `Série com menos de 12 meses (início em ${date(issue.date)}): fora de rankings e pares.`;

const repeatedQuota = (issue: Issue): string => {
  const count = issue.days ?? 0;
  return `Mesma cota em ${plural(count, "informe seguido", "informes seguidos")}, de ${date(issue.date)} a ${date(issue.end_date)}.`;
};

const staleSource = (issue: Issue): string => {
  const source = issue.detail === null ? "Fonte" : sourceLabel(issue.detail);
  if (issue.date === null) return `${source} sem nenhuma data disponível.`;
  const notes = [
    issue.days === null ? null : `${businessDays(issue.days)} de atraso`,
    issue.threshold === null ? null : `tolerância de ${businessDays(issue.threshold)}`,
  ].filter((note) => note !== null);
  const suffix = notes.length === 0 ? "" : ` (${notes.join("; ")})`;
  return `${source} com dados até ${date(issue.date)}, esperado até ${date(issue.end_date)}${suffix}.`;
};

const registryMismatch = (issue: Issue): string => {
  if (issue.detail === "registered but never reported")
    return "Série no cadastro da CVM sem nenhum informe diário publicado.";
  if (issue.detail === "reported but not registered") {
    const count = issue.days === null ? "" : ` (${plural(issue.days, "informe", "informes")})`;
    return `Informes publicados de ${date(issue.date)} a ${date(issue.end_date)}${count} para série ausente do cadastro da CVM.`;
  }
  return "Divergência entre o cadastro da CVM e o informe diário.";
};

const fallback = (issue: Issue): string => {
  const when = issue.date === null ? "" : ` em ${date(issue.date)}`;
  const detail = issue.detail === null ? "" : ` (${issue.detail})`;
  return `${ruleLabel(issue.rule)}${when}${detail}.`;
};

const BUILDERS: Record<string, (issue: Issue) => string> = {
  zero_values: zeroValues,
  duplicate_report: duplicateReport,
  quota_jump: quotaJump,
  unexplained_net_assets: unexplainedNetAssets,
  missing_report: missingReport,
  short_history: shortHistory,
  repeated_quota: repeatedQuota,
  stale_source: staleSource,
  registry_mismatch: registryMismatch,
};

export const issueText = (issue: Issue): string => (BUILDERS[issue.rule] ?? fallback)(issue);

export const issueSpan = (issue: Issue): string =>
  issue.end_date === null || issue.end_date === issue.date
    ? date(issue.date)
    : `de ${date(issue.date)} a ${date(issue.end_date)}`;

const RATIO_RULES = new Set(["quota_jump", "unexplained_net_assets"]);

export const issueMeasure = (issue: Issue): string | null => {
  if (!RATIO_RULES.has(issue.rule) || issue.value === null) return null;
  const value = percent2(issue.value);
  return issue.threshold === null ? value : `${value} / ${percent2(issue.threshold)}`;
};

export const issueMagnitude = (issue: Issue): number | null =>
  RATIO_RULES.has(issue.rule) && issue.value !== null ? Math.abs(issue.value) : null;
