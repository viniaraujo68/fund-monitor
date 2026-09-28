<script lang="ts">
  import { benchmarkSlot, FUND_SLOT } from "$lib/charts/palette";
  import type { FundDetail } from "$lib/data/types";
  import { monthEndIndexes } from "$lib/fund";
  import { axisNumber, DASH, date, monthLabel, ratio2 } from "$lib/format";
  import { benchmarkLabel, benchmarkList } from "$lib/labels";
  import ChartCard from "./ChartCard.svelte";
  import LineChart, { type LineSeries } from "./LineChart.svelte";

  const { detail }: { detail: FundDetail } = $props();

  const summary = $derived(detail.summary);
  const dates = $derived(detail.cumulative.dates);
  const benchmarks = $derived(
    summary.benchmarks.filter((benchmark) => detail.cumulative.values[benchmark] !== undefined),
  );

  const lines = $derived<LineSeries[]>([
    { label: summary.display_name, slot: FUND_SLOT, data: detail.cumulative.values.fund ?? [] },
    ...benchmarks.map((benchmark) => ({
      label: benchmarkLabel(benchmark),
      slot: benchmarkSlot(benchmark),
      data: detail.cumulative.values[benchmark] ?? [],
    })),
  ]);

  const monthEnds = $derived(monthEndIndexes(dates));
  const first = $derived(dates[0]);
  const last = $derived(dates.at(-1));

  const note = $derived(
    first === undefined
      ? undefined
      : `Base 100 em ${date(first)}. Cota líquida de taxa de administração, sem ajuste por come-cotas.`,
  );

  const valueAt = (key: string, index: number): string => {
    const value = detail.cumulative.values[key]?.[index];
    return value === null || value === undefined ? DASH : ratio2(value);
  };
</script>

<ChartCard title="Retorno acumulado contra o benchmark" {note}>
  {#snippet chart()}
    <LineChart
      labels={dates.map(date)}
      series={lines}
      formatValue={ratio2}
      formatAxis={axisNumber}
      axisTitle="base 100"
      ariaLabel={`Retorno acumulado de ${summary.display_name} contra ${benchmarkList(benchmarks)}, base 100, de ${date(first)} a ${date(last)}`}
      insufficientText="A série ainda não tem pontos suficientes para desenhar o retorno acumulado."
    />
  {/snippet}
  {#snippet table()}
    {#if monthEnds.length === 0}
      <p class="text-base-content/70 py-6 text-center text-sm">
        A série ainda não tem cotas para montar a tabela.
      </p>
    {:else}
      <table class="table-sm table">
        <caption class="sr-only">Retorno acumulado no fim de cada mês, base 100</caption>
        <thead>
          <tr>
            <th scope="col">Mês</th>
            <th scope="col" class="text-right">Fundo</th>
            {#each benchmarks as benchmark (benchmark)}
              <th scope="col" class="text-right">{benchmarkLabel(benchmark)}</th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each monthEnds as index (index)}
            <tr>
              <th scope="row" class="font-normal" title={date(dates[index])}>
                {monthLabel(dates[index] ?? "")}
              </th>
              <td class="text-right tabular-nums">{valueAt("fund", index)}</td>
              {#each benchmarks as benchmark (benchmark)}
                <td class="text-right tabular-nums">{valueAt(benchmark, index)}</td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {/snippet}
</ChartCard>
