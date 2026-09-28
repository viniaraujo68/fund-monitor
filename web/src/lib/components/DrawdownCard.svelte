<script lang="ts">
  import { DRAWDOWN_SLOT } from "$lib/charts/palette";
  import type { FundDetail, RiskRow } from "$lib/data/types";
  import { DASH, date, integer, percent2, percentShort } from "$lib/format";
  import { windowLabel } from "$lib/labels";
  import ChartCard from "./ChartCard.svelte";
  import ChartNotice from "./ChartNotice.svelte";
  import LineChart from "./LineChart.svelte";

  const { detail }: { detail: FundDetail } = $props();

  const dates = $derived(detail.drawdown.dates);
  const values = $derived(detail.drawdown.values.fund ?? []);
  const flat = $derived(values.every((value) => value === null || value === 0));

  const dated = (value: number | null, day: string | null): string =>
    value === null ? DASH : `${percent2(value)} em ${date(day)}`;

  const episode = (row: RiskRow): string | null => (row.peak_date === null ? "sem queda" : null);

  const MEASURES: { label: string; read: (row: RiskRow) => string }[] = [
    { label: "Drawdown máximo", read: (row) => percent2(row.max_drawdown) },
    { label: "Pico", read: (row) => episode(row) ?? date(row.peak_date) },
    { label: "Vale", read: (row) => episode(row) ?? date(row.trough_date) },
    {
      label: "Recuperação",
      read: (row) =>
        episode(row) ?? (row.recovery_date === null ? "sem recuperação" : date(row.recovery_date)),
    },
    { label: "Melhor dia", read: (row) => dated(row.best_day, row.best_day_date) },
    { label: "Pior dia", read: (row) => dated(row.worst_day, row.worst_day_date) },
    { label: "Dias positivos", read: (row) => percent2(row.positive_days_share) },
    { label: "Observações", read: (row) => integer(row.observations) },
  ];
</script>

<ChartCard title="Drawdown" note="Queda em relação à máxima histórica da cota na janela.">
  {#snippet chart()}
    {#if flat && values.length >= 2}
      <ChartNotice text="A cota não ficou abaixo da própria máxima em nenhum dia da janela." />
    {:else}
      <LineChart
        labels={dates.map(date)}
        series={[{ label: "Drawdown", slot: DRAWDOWN_SLOT, data: values }]}
        formatValue={percent2}
        formatAxis={percentShort}
        fill
        points={false}
        max={0}
        ariaLabel={`Drawdown de ${detail.summary.display_name} de ${date(dates[0])} a ${date(dates.at(-1))}`}
        insufficientText="A série ainda não tem pontos suficientes para desenhar o drawdown."
      />
    {/if}
  {/snippet}
  {#snippet table()}
    {#if detail.risk.length === 0}
      <p class="text-base-content/70 py-6 text-center text-sm">
        Menos de 12 meses de série: ainda não há janela de risco.
      </p>
    {:else}
      <table class="table-sm table">
        <caption class="sr-only">Episódios de drawdown e dias extremos por janela</caption>
        <thead>
          <tr>
            <th scope="col"><span class="sr-only">Medida</span></th>
            {#each detail.risk as row (row.window)}
              <th scope="col" class="text-right">{windowLabel(row.window)}</th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each MEASURES as measure (measure.label)}
            <tr>
              <th scope="row" class="font-normal">{measure.label}</th>
              {#each detail.risk as row (row.window)}
                <td class="text-right whitespace-nowrap tabular-nums">{measure.read(row)}</td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {/snippet}
</ChartCard>
