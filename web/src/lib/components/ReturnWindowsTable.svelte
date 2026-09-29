<script lang="ts">
  import { DataTable, type Column } from "@viniaraujo68/plinth/table";
  import type { FundDetail, WindowRow } from "$lib/data/types";
  import { CDI, marketBenchmarks } from "$lib/fund";
  import { date, integer, percent2, percentPoints } from "$lib/format";
  import { benchmarkLabel, windowLabel } from "$lib/labels";

  const { detail }: { detail: FundDetail } = $props();

  const benchmarks = $derived(marketBenchmarks(detail.summary));

  const ANNUALIZATION_HIDDEN = "12m";

  const excessOver = (row: WindowRow, benchmark: string): number | null =>
    row.excess_returns[benchmark] ?? null;

  const benchmarkReturn = (row: WindowRow, benchmark: string): number | null =>
    row.benchmark_returns[benchmark] ?? null;

  type Metric = {
    key: string;
    label: string;
    read: (row: WindowRow) => number | null;
    format: (value: number | null) => string;
  };

  const metrics = $derived<Metric[]>([
    { key: "fund_return", label: "Fundo", read: (row) => row.fund_return, format: percent2 },
    { key: "cdi_return", label: "CDI", read: (row) => row.cdi_return, format: percent2 },
    { key: "pct_cdi", label: "% do CDI", read: (row) => row.pct_cdi, format: percent2 },
    ...benchmarks.map((benchmark) => ({
      key: `benchmark_${benchmark}`,
      label: benchmarkLabel(benchmark),
      read: (row: WindowRow) => benchmarkReturn(row, benchmark),
      format: percent2,
    })),
    {
      key: "excess_cdi",
      label: "vs CDI",
      read: (row) => excessOver(row, CDI),
      format: percentPoints,
    },
    ...benchmarks.map((benchmark) => ({
      key: `excess_${benchmark}`,
      label: `vs ${benchmarkLabel(benchmark)}`,
      read: (row: WindowRow) => excessOver(row, benchmark),
      format: percentPoints,
    })),
    {
      key: "fund_annualized",
      label: "Anualizado",
      read: (row) => (row.window === ANNUALIZATION_HIDDEN ? null : row.fund_annualized),
      format: percent2,
    },
  ]);

  const columns = $derived<Column<WindowRow>[]>([
    {
      key: "window",
      label: "Janela",
      sortable: false,
      class: "whitespace-nowrap",
      value: (row) => windowLabel(row.window),
    },
    { key: "period", label: "Período", sortable: false, cell: periodText },
    ...metrics.map((metric) => ({
      key: metric.key,
      label: metric.label,
      numeric: true,
      sortable: false,
      class: "whitespace-nowrap",
      value: (row: WindowRow) => metric.format(metric.read(row)),
    })),
  ]);
</script>

{#snippet periodText(row: WindowRow)}
  {#if row.base_date === null}
    <span class="text-base-content/70">sem histórico</span>
  {:else}
    <span class="whitespace-nowrap tabular-nums">{date(row.base_date)} a {date(row.end_date)}</span>
    {#if row.business_days !== null}
      <span class="text-base-content/70 block text-xs tabular-nums">
        {integer(row.business_days)}
        {row.business_days === 1 ? "dia útil" : "dias úteis"}
      </span>
    {/if}
  {/if}
{/snippet}

{#snippet windowCard(row: WindowRow)}
  <div class="flex flex-col gap-2">
    <div class="flex flex-wrap items-baseline justify-between gap-x-3">
      <span class="font-medium">{windowLabel(row.window)}</span>
      <span class="text-right text-sm">{@render periodText(row)}</span>
    </div>
    <dl class="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
      {#each metrics as metric (metric.key)}
        <div class="flex items-baseline justify-between gap-2">
          <dt class="text-base-content/70 text-xs">{metric.label}</dt>
          <dd class="tabular-nums">{metric.format(metric.read(row))}</dd>
        </div>
      {/each}
    </dl>
  </div>
{/snippet}

{#snippet noWindows()}
  <p class="text-base-content/70 py-6 text-center text-sm">Nenhuma janela calculada.</p>
{/snippet}

<section class="card bg-base-100 border-base-content/10 border" aria-labelledby="windows-title">
  <div class="card-body gap-3 p-4 sm:p-5">
    <div class="flex flex-col gap-1">
      <h2 id="windows-title" class="text-base font-semibold">Janelas de retorno</h2>
      <p class="text-base-content/70 text-xs">
        % do CDI em toda janela com CDI positivo. "vs" é a diferença, em pontos percentuais, entre o retorno do
        fundo e o do benchmark na mesma janela. Anualizado só em 24 meses e desde o início com um ano ou mais: em 12
        meses ele quase repete o acumulado.
      </p>
    </div>
    <DataTable
      rows={detail.windows}
      {columns}
      rowKey={(row) => row.window}
      locale="pt-BR"
      label="Retorno por janela"
      class="table-sm"
      card={windowCard}
      empty={noWindows}
    />
  </div>
</section>
