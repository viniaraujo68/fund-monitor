import type { Issue } from "$lib/data/types";
import { date, integer, monthName, percent2, percentShort } from "$lib/format";
import { benchmarkLabel, countsAsOpen, severityRank, sourceLabel } from "$lib/labels";

export const RULE_LABELS: Record<string, string> = {
  missing_report: "Dia sem informe",
  quota_jump: "Salto de cota",
  repeated_quota: "Cota repetida",
  unexplained_net_assets: "PL sem explicação",
  zero_values: "Valores zerados",
  short_history: "Histórico curto",
  duplicate_report: "Informe duplicado",
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
  missing_report: {
    detects: "Dia útil sem informe depois do início da série.",
    threshold: "qualquer dia útil sem informe",
    severity: "Baixa; média a partir de 5 dias úteis seguidos",
  },
  quota_jump: {
    detects: "Variação diária da cota fora do padrão recente da série.",
    threshold: "desvio da média de 60 dias acima de 5σ e de 0,1 % da cota; 3 % absoluto em RF",
    severity:
      "Média; informativo em dia de mercado: o Ibovespa ou o IMA-B, o que mais se parece com o fundo, também saiu do padrão no mesmo sentido, ou ≥ 10 % da classe saltou",
  },
  repeated_quota: {
    detects: "Mesma cota em informes seguidos, sinal de cota não atualizada.",
    threshold: "3 ou mais informes seguidos",
    severity: "Média",
  },
  unexplained_net_assets: {
    detects: "Variação mensal do PL que captação líquida e rentabilidade não explicam.",
    threshold: "resíduo acima de 1 % do PL do início do mês, em módulo",
    severity: "Média",
  },
  zero_values: {
    detects: "Informe publicado com cota, PL ou número de cotistas zerado.",
    threshold: "cota ≤ 0, PL ≤ 0 ou nenhum cotista",
    severity: "Alta",
  },
  short_history: {
    detects: "Série com menos de 12 meses, sem % do CDI e fora dos pares.",
    threshold: "sem retorno na janela de 12 meses",
    severity: "Informativo",
  },
  duplicate_report: {
    detects: "Mais de um informe da mesma série no mesmo dia, com valores diferentes.",
    threshold: "2 ou mais informes no dia com algum valor divergente",
    severity: "Média",
  },
  stale_source: {
    detects: "Fonte de dados sem atualização recente, contada em dias de semana (sem descontar feriados).",
    threshold: "atraso > 2 dias de semana no informe CVM, > 1 nos índices",
    severity: "Média; alta com mais de 3 dias de semana além da tolerância ou sem dado",
  },
  registry_mismatch: {
    detects: "Série no cadastro sem informe, ou informe de série fora do cadastro ou inativa nele.",
    threshold: "qualquer divergência",
    severity: "Média",
  },
};

const JUMP_FLOOR = 0.001;
const FLOOR_TOLERANCE = 1e-9;

const PLURAL_FIELDS = new Set(["inflows", "outflows", "shareholders"]);

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

const weekdays = (count: number): string => plural(count, "dia de semana", "dias de semana");

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
  const singular = differing.length === 1 && !PLURAL_FIELDS.has(differing[0] ?? "");
  const differingPart =
    differing.length === 0
      ? " com valores diferentes"
      : ` com ${fieldList(differing)} ${singular ? "diferente" : "diferentes"}`;
  return `${countWord} informes em ${date(issue.date)}${typesPart}${differingPart}.`;
};

type JumpLimit = "absolute" | "floor" | "sigma";

const jumpFlags = (issue: Issue): string[] =>
  (issue.detail ?? "").split(";").map((flag) => flag.trim());

const jumpLimit = (issue: Issue): JumpLimit => {
  if (jumpFlags(issue).includes("absolute")) return "absolute";
  return issue.threshold === null || issue.threshold <= JUMP_FLOOR + FLOOR_TOLERANCE ? "floor" : "sigma";
};

const jumpThreshold = (issue: Issue): number | null =>
  jumpLimit(issue) === "floor" ? Math.max(issue.threshold ?? 0, JUMP_FLOOR) : issue.threshold;

const JUMP_LIMIT_NAMES: Record<JumpLimit, string> = {
  absolute: "absoluto",
  floor: "piso",
  sigma: "5σ",
};

const INDEX_FLAG = "index ";
const MARKET_FLAG = "market-wide";

const jumpIndex = (issue: Issue): string | null => {
  const flag = jumpFlags(issue).find((part) => part.startsWith(INDEX_FLAG));
  return flag === undefined ? null : flag.slice(INDEX_FLAG.length).trim();
};

const jumpReason = (issue: Issue): string => {
  const index = jumpIndex(issue);
  if (index !== null)
    return `dia de mercado: o ${benchmarkLabel(index)} também saiu do padrão no mesmo sentido`;
  if (jumpFlags(issue).includes(MARKET_FLAG))
    return "dia de mercado: pelo menos 10 % dos fundos da mesma classificação saltaram";
  return jumpLimit(issue) === "absolute"
    ? "acima do limite absoluto de 3 % para renda fixa"
    : "fora do padrão da própria série e não explicado pelo mercado";
};

const quotaJump = (issue: Issue): string =>
  `Salto de ${percent2(issue.value)} na cota em ${date(issue.date)}; ${jumpReason(issue)}.`;

const unexplainedNetAssets = (issue: Issue): string => {
  const month = issue.date === null ? "No mês" : `Em ${monthName(issue.date)}`;
  const magnitude = issue.value === null ? null : Math.abs(issue.value);
  return `${month} o PL variou ${percent2(magnitude)} além do que captação e rentabilidade explicam (limite ${percentShort(issue.threshold)} do PL do início do mês).`;
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
  `Série com menos de 12 meses (início em ${date(issue.date)}): sem % do CDI e fora dos pares.`;

const repeatedQuota = (issue: Issue): string => {
  const count = issue.days ?? 0;
  return `Mesma cota em ${plural(count, "informe seguido", "informes seguidos")}, de ${date(issue.date)} a ${date(issue.end_date)}.`;
};

const staleSource = (issue: Issue): string => {
  const source = issue.detail === null ? "Fonte" : sourceLabel(issue.detail);
  if (issue.date === null) return `${source} sem nenhuma data disponível.`;
  const notes = [
    issue.days === null ? null : `${weekdays(issue.days)} de atraso`,
    issue.threshold === null ? null : `tolerância de ${weekdays(issue.threshold)}`,
  ].filter((note) => note !== null);
  const suffix = notes.length === 0 ? "" : ` (${notes.join("; ")})`;
  return `${source} com dados até ${date(issue.date)}, esperado até ${date(issue.end_date)}${suffix}.`;
};

const registryMismatch = (issue: Issue): string => {
  if (issue.detail === "registered but never reported")
    return "Série no cadastro da CVM sem nenhum informe diário publicado.";
  const count = issue.days === null ? "" : ` (${plural(issue.days, "informe", "informes")})`;
  const span = `de ${date(issue.date)} a ${date(issue.end_date)}${count}`;
  if (issue.detail === "reported but not registered")
    return `Informes publicados ${span} para série ausente do cadastro da CVM.`;
  if (issue.detail === "reported but not active")
    return `Informes publicados ${span} para série que o cadastro da CVM não lista como ativa.`;
  return "Divergência entre o cadastro da CVM e o informe diário.";
};

const fallback = (issue: Issue): string => {
  const when = issue.date === null ? "" : ` em ${date(issue.date)}`;
  const detail = issue.detail === null ? "" : ` (${issue.detail})`;
  return `${ruleLabel(issue.rule)}${when}${detail}.`;
};

const BUILDERS: Record<string, (issue: Issue) => string> = {
  missing_report: missingReport,
  quota_jump: quotaJump,
  repeated_quota: repeatedQuota,
  unexplained_net_assets: unexplainedNetAssets,
  zero_values: zeroValues,
  short_history: shortHistory,
  duplicate_report: duplicateReport,
  stale_source: staleSource,
  registry_mismatch: registryMismatch,
};

export const issueText = (issue: Issue): string => (BUILDERS[issue.rule] ?? fallback)(issue);

export const issueSpan = (issue: Issue): string =>
  issue.end_date === null || issue.end_date === issue.date
    ? date(issue.date)
    : `de ${date(issue.date)} a ${date(issue.end_date)}`;

const RATIO_RULES = new Set(["quota_jump", "unexplained_net_assets"]);

export interface IssueMeasure {
  value: string;
  limit: string | null;
  note: string | null;
}

const jumpDeviationMeasured = (issue: Issue): boolean =>
  jumpLimit(issue) !== "absolute" && issue.deviation !== null;

export const issueMeasure = (issue: Issue): IssueMeasure | null => {
  if (!RATIO_RULES.has(issue.rule) || issue.value === null) return null;
  if (issue.rule === "quota_jump") {
    const threshold = jumpThreshold(issue);
    const limit =
      threshold === null ? null : `limite ±${percent2(threshold)} (${JUMP_LIMIT_NAMES[jumpLimit(issue)]})`;
    if (jumpDeviationMeasured(issue))
      return {
        value: `desvio ${percent2(issue.deviation)}`,
        limit,
        note: `retorno do dia ${percent2(issue.value)}`,
      };
    return { value: `retorno ${percent2(issue.value)}`, limit, note: null };
  }
  return {
    value: `resíduo ${percent2(issue.value)}`,
    limit: issue.threshold === null ? null : `limite ±${percent2(issue.threshold)}`,
    note: null,
  };
};

export const issueMeasureText = (issue: Issue): string | null => {
  const measure = issueMeasure(issue);
  if (measure === null) return null;
  const main = measure.limit === null ? measure.value : `${measure.value} / ${measure.limit}`;
  return measure.note === null ? main : `${main} · ${measure.note}`;
};

export const issueMagnitude = (issue: Issue): number | null => {
  if (!RATIO_RULES.has(issue.rule) || issue.value === null) return null;
  if (issue.rule === "quota_jump" && jumpDeviationMeasured(issue)) return Math.abs(issue.deviation ?? 0);
  return Math.abs(issue.value);
};

export const isOpenIssue = (issue: Issue): boolean => countsAsOpen(issue.status, issue.severity);

export const triageRank = (issue: Issue): number =>
  (isOpenIssue(issue) ? 0 : 1) * 10 + severityRank(issue.severity);

export const byTriage = (left: Issue, right: Issue): number =>
  triageRank(left) - triageRank(right) || (right.date ?? "").localeCompare(left.date ?? "");

export const triageDetail = (note: string | null, treatedOn: string | null): string =>
  [note, treatedOn === null ? null : `tratado em ${date(treatedOn)}`]
    .filter((part) => part !== null && part !== "")
    .join(" · ");
