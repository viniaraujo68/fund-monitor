import type { FundDetail, FundSummary, RiskRow, WindowRow } from "$lib/data/types";

export const CDI = "cdi";

export const findWindow = (detail: FundDetail, key: string): WindowRow | undefined =>
  detail.windows.find((row) => row.window === key);

export const findRisk = (detail: FundDetail, key: string): RiskRow | undefined =>
  detail.risk.find((row) => row.window === key);

export const hasHistory = (row: WindowRow | undefined): boolean =>
  row !== undefined && row.base_date !== null;

export const marketBenchmarks = (summary: FundSummary): string[] =>
  summary.benchmarks.filter((benchmark) => benchmark !== CDI);

export const monthEndIndexes = (dates: string[]): number[] =>
  dates.flatMap((day, index) =>
    index === dates.length - 1 || dates[index + 1]?.slice(0, 7) !== day.slice(0, 7) ? [index] : [],
  );

export const difference = (left: number | null, right: number | null): number | null =>
  left === null || right === null ? null : left - right;
