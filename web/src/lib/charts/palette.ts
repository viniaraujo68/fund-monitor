export const FUND_SLOT = 1;

export const BENCHMARK_SLOT: Record<string, number> = {
  cdi: 3,
  ima_b: 0,
  ibov: 2,
};

export const INFLOW_SLOT = 3;
export const OUTFLOW_SLOT = 4;
export const DRAWDOWN_SLOT = 4;

export const CLASSIFICATION_SLOT: Record<string, number> = {
  "Renda Fixa": 0,
  Multimercado: 1,
  Ações: 2,
};

export const benchmarkSlot = (benchmark: string): number => BENCHMARK_SLOT[benchmark] ?? 0;

export const classificationSlot = (classification: string): number =>
  CLASSIFICATION_SLOT[classification] ?? 0;
