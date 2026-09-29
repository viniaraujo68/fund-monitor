import type { FundDetail, FundSummary, IsoDate, PeerPosition, RiskRow, WindowRow } from "$lib/data/types";
import { GENERAL_PUBLIC } from "$lib/labels";

export const CDI = "cdi";

export const MIN_PEERS = 5;

export const DI_BENCHMARK = "DI de um dia";

export const SHARPE_HIDDEN_REASON = "Sharpe não exibido em fundo DI: vol perto de zero torna a razão instável";

export const hidesSharpe = (summary: FundSummary): boolean =>
  summary.performance_benchmark === DI_BENCHMARK;

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

export const hasPeerGroup = (peers: PeerPosition | null): peers is PeerPosition =>
  peers !== null && peers.peer_count >= MIN_PEERS;

export const peerGapReason = (summary: FundSummary): string => {
  if (summary.target_audience !== GENERAL_PUBLIC) return "só para Público Geral";
  if (summary.return_12m === null) return "menos de 12 meses de série";
  if (summary.peer_count < MIN_PEERS) return `menos de ${MIN_PEERS} pares na classificação`;
  return "sem grupo de pares";
};

const monthEnd = (day: IsoDate): IsoDate => {
  const [year, month] = day.split("-").map(Number);
  return new Date(Date.UTC(year ?? 1970, month ?? 1, 0)).toISOString().slice(0, 10);
};

export const isPartialMonth = (month: IsoDate, lastDate: IsoDate | null): boolean =>
  lastDate !== null && lastDate.slice(0, 7) === month.slice(0, 7) && lastDate < monthEnd(month);
