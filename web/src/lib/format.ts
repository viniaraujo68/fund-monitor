import { createFormatters } from "@viniaraujo68/plinth/formatters";

export const DASH = "—";

type Maybe = number | null | undefined;

const base = createFormatters("pt-BR", {
  datetime: { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" },
  number: { maximumFractionDigits: 0 },
  percent: { minimumFractionDigits: 2, maximumFractionDigits: 2 },
});

const ratioFormat = createFormatters("pt-BR", {
  number: { minimumFractionDigits: 2, maximumFractionDigits: 2 },
});

const shortPercentFormat = createFormatters("pt-BR", {
  percent: { minimumFractionDigits: 0, maximumFractionDigits: 2 },
});

const wholePercentFormat = createFormatters("pt-BR", {
  percent: { minimumFractionDigits: 0, maximumFractionDigits: 0 },
});

const monthFormat = createFormatters("pt-BR", {
  date: { dateStyle: undefined, month: "short", year: "2-digit" },
});

const monthNameFormat = createFormatters("pt-BR", {
  date: { dateStyle: undefined, month: "long", year: "numeric" },
});

const AXIS_MAX_DIGITS = 4;

const axisFormats = Array.from({ length: AXIS_MAX_DIGITS + 1 }, (_, digits) =>
  createFormatters("pt-BR", {
    number: { minimumFractionDigits: digits, maximumFractionDigits: digits },
    percent: { minimumFractionDigits: digits, maximumFractionDigits: digits },
  }),
);

const stepDigits = (step: number): number => {
  if (!(step > 0) || !Number.isFinite(step)) return 0;
  for (let digits = 0; digits < AXIS_MAX_DIGITS; digits += 1) {
    const scaled = step * 10 ** digits;
    if (Math.abs(scaled - Math.round(scaled)) < 1e-6) return digits;
  }
  return AXIS_MAX_DIGITS;
};

const axisFormat = (step: number) => axisFormats[stepDigits(step)] ?? base;

const compactMoneyFormat = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
});

const orDash = (value: string | null): string => value ?? DASH;

export const percent2 = (value: Maybe): string => orDash(base.percent(value));

export const percentShort = (value: Maybe): string => orDash(shortPercentFormat.percent(value));

export const percentWhole = (value: Maybe): string => orDash(wholePercentFormat.percent(value));

export const ratio2 = (value: Maybe): string => orDash(ratioFormat.number(value));

export const axisNumber = (value: number, step: number): string =>
  orDash(axisFormat(step).number(value === 0 ? 0 : value));

export const axisPercent = (value: number, step: number): string =>
  orDash(axisFormat(step * 100).percent(value === 0 ? 0 : value));

export const integer = (value: Maybe): string => orDash(base.number(value));

export const money = (value: Maybe): string => orDash(base.currency(value, "BRL", "axis"));

export const moneyCompact = (value: Maybe): string =>
  value === null || value === undefined ? DASH : compactMoneyFormat.format(value);

export const date = (value: string | null | undefined): string => orDash(base.date(value));

export const datetime = (value: string | null | undefined): string =>
  orDash(base.datetime(value));

export const monthLabel = (value: string): string =>
  monthFormat.date(value).replace(/\.? de /, "/");

export const monthName = (value: string): string => monthNameFormat.date(value);

export const cnpj = (value: string): string => {
  const digits = value.replace(/\D/g, "");
  if (digits.length !== 14) return value;
  return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`;
};

export const percentileLabel = (value: Maybe): string =>
  value === null || value === undefined ? DASH : `P${Math.round(value * 100)}`;

export const peerRank = (percentile: Maybe, peerCount: number): string =>
  percentile === null || percentile === undefined || peerCount === 0
    ? DASH
    : `${percentileLabel(percentile)} · ${integer(peerCount)} ${peerCount === 1 ? "par" : "pares"}`;
