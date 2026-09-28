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

const monthFormat = createFormatters("pt-BR", {
  date: { dateStyle: undefined, month: "short", year: "2-digit" },
});

const monthNameFormat = createFormatters("pt-BR", {
  date: { dateStyle: undefined, month: "long", year: "numeric" },
});

const compactMoneyFormat = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
});

const orDash = (value: string | null): string => value ?? DASH;

export const percent2 = (value: Maybe): string => orDash(base.percent(value));

export const percentShort = (value: Maybe): string => orDash(shortPercentFormat.percent(value));

export const ratio2 = (value: Maybe): string => orDash(ratioFormat.number(value));

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
