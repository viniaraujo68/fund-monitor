<script lang="ts">
  import { INFLOW_SLOT, OUTFLOW_SLOT } from "$lib/charts/palette";
  import { slotVar } from "$lib/charts/theme";
  import type { FundDetail } from "$lib/data/types";
  import { isPartialMonth } from "$lib/fund";
  import { date, integer, money, moneyCompact, monthLabel, percent2 } from "$lib/format";
  import BarChart, { type BarSeries } from "./BarChart.svelte";
  import ChartCard from "./ChartCard.svelte";

  const { detail }: { detail: FundDetail } = $props();

  const RESIDUAL_LIMIT = 0.01;
  const MIN_CHART_MONTHS = 2;
  const RESIDUAL_NOTE =
    "Resíduo do PL: variação do patrimônio que captação líquida e rentabilidade não explicam, em proporção do PL do início do mês.";

  const flows = $derived(detail.monthly_flows);
  const lastMonth = $derived(flows.at(-1)?.month);
  const lastDate = $derived(detail.summary.last_date);

  const partial = $derived(lastMonth !== undefined && isPartialMonth(lastMonth, lastDate));

  const note = $derived(
    [
      partial && lastMonth !== undefined
        ? `${monthLabel(lastMonth)} parcial, até ${date(lastDate)}.`
        : null,
      RESIDUAL_NOTE,
    ]
      .filter((part) => part !== null)
      .join(" "),
  );

  const bars = $derived<BarSeries[]>([
    {
      label: "Captação líquida",
      slot: INFLOW_SLOT,
      data: flows.map((row) => row.net_flow),
      colors: flows.map((row) => ((row.net_flow ?? 0) < 0 ? OUTFLOW_SLOT : INFLOW_SLOT)),
    },
  ]);

  const LEGEND = [
    { label: "Entrada líquida", slot: INFLOW_SLOT },
    { label: "Saída líquida", slot: OUTFLOW_SLOT },
  ];

  const unexplained = (value: number | null): boolean =>
    value !== null && Math.abs(value) > RESIDUAL_LIMIT;
</script>

<ChartCard title="Captação líquida mensal" {note}>
  {#snippet chart()}
    <div class="flex flex-col gap-2">
      {#if flows.length >= MIN_CHART_MONTHS}
        <ul class="text-base-content/70 flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="Legenda">
          {#each LEGEND as entry (entry.label)}
            <li class="flex items-center gap-1.5">
              <span
                class="inline-block size-2.5 rounded-sm"
                style:background-color={slotVar(entry.slot)}
                aria-hidden="true"
              ></span>
              {entry.label}
            </li>
          {/each}
        </ul>
      {/if}
      <BarChart
        labels={flows.map((row) => monthLabel(row.month))}
        series={bars}
        formatValue={money}
        formatAxis={moneyCompact}
        ariaLabel={`Captação líquida mensal de ${detail.summary.display_name}, ${flows.length} meses`}
        insufficientText="A série ainda não tem meses suficientes para desenhar a captação."
      />
    </div>
  {/snippet}
  {#snippet table()}
    {#if flows.length === 0}
      <p class="text-base-content/70 py-6 text-center text-sm">
        A série ainda não tem meses de captação para montar a tabela.
      </p>
    {:else}
      <table class="table-sm table">
        <caption class="sr-only">Captação, resgates e patrimônio por mês</caption>
        <thead>
          <tr>
            <th scope="col">Mês</th>
            <th scope="col" class="text-right">Captação</th>
            <th scope="col" class="text-right">Resgate</th>
            <th scope="col" class="text-right">Líquido</th>
            <th scope="col" class="text-right">PL no fim</th>
            <th scope="col" class="text-right">Cotistas</th>
            <th scope="col" class="text-right">Retorno no mês</th>
            <th scope="col" class="text-right">Resíduo do PL</th>
          </tr>
        </thead>
        <tbody>
          {#each flows as row (row.month)}
            <tr>
              <th scope="row" class="font-normal whitespace-nowrap">{monthLabel(row.month)}</th>
              <td class="text-right whitespace-nowrap tabular-nums">{money(row.inflows)}</td>
              <td class="text-right whitespace-nowrap tabular-nums">{money(row.outflows)}</td>
              <td class="text-right font-medium whitespace-nowrap tabular-nums">
                {money(row.net_flow)}
              </td>
              <td class="text-right whitespace-nowrap tabular-nums">{money(row.net_assets_end)}</td>
              <td class="text-right tabular-nums">{integer(row.shareholders_end)}</td>
              <td class="text-right tabular-nums">{percent2(row.monthly_return)}</td>
              <td
                class={[
                  "text-right tabular-nums",
                  unexplained(row.unexplained_share) && "text-warning font-medium",
                ]}
              >
                {percent2(row.unexplained_share)}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {/snippet}
</ChartCard>
