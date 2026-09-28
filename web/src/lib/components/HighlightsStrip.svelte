<script lang="ts">
  import { resolve } from "$app/paths";
  import { INFLOW_SLOT, OUTFLOW_SLOT } from "$lib/charts/palette";
  import HorizontalBarChart, {
    type HorizontalBar,
  } from "$lib/components/HorizontalBarChart.svelte";
  import { date, integer, moneyCompact, peerRank, percent2 } from "$lib/format";
  import type { FlowHighlight, HighlightFund, Highlights } from "$lib/highlights";

  const { highlights }: { highlights: Highlights } = $props();

  const WARNING_ICON = [
    "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3",
    "M12 9v4",
    "M12 17h.01",
  ];

  const flowBars = (flow: FlowHighlight, sign: 1 | -1): HorizontalBar[] =>
    flow.bars.map((bar) => ({
      id: bar.seriesId,
      label: bar.partial ? `${bar.name}*` : bar.name,
      value: bar.netFlow * sign,
    }));

  const fundCount = (count: number): string => (count === 1 ? "fundo" : "fundos");

  const seriesCount = (count: number): string => (count === 1 ? "série" : "séries");
</script>

{#snippet fundLink(fund: HighlightFund)}
  {#if fund.linked}
    <a class="link link-hover" href={resolve("/fundo/[id]", { id: fund.seriesId })}>{fund.name}</a>
  {:else}
    <span>{fund.name}</span>
  {/if}
{/snippet}

{#snippet flowCard(title: string, flow: FlowHighlight, sign: 1 | -1, slot: number, label: string)}
  <article class="card bg-base-100 border-base-content/10 border">
    <div class="card-body gap-3 p-4 sm:p-5">
      <h3 class="text-sm font-semibold">{title}</h3>
      <HorizontalBarChart
        rows={flowBars(flow, sign)}
        formatValue={(value) => moneyCompact(value * sign)}
        ariaLabel={label}
        limit={flow.bars.length}
        positiveSlot={slot}
        negativeSlot={slot}
      />
      {#if flow.hasPartial}
        <p class="text-base-content/70 grow-0 text-xs">
          * janela parcial: menos de 12 meses de captação.
        </p>
      {/if}
    </div>
  </article>
{/snippet}

<section class="flex flex-col gap-2" aria-labelledby="highlights-title">
  <div class="flex flex-col gap-0.5">
    <h2 id="highlights-title" class="text-base font-semibold">Destaques</h2>
    <p class="text-base-content/70 text-xs">
      Público Geral, sem veículos estruturais, 12 meses até {date(highlights.asOf)}. Não segue os
      filtros da página.
    </p>
  </div>

  <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
    {#if highlights.cdi}
      {@const cdi = highlights.cdi}
      <article class="card bg-base-100 border-base-content/10 border">
        <div class="card-body gap-3 p-4 sm:p-5">
          <h3 class="text-sm font-semibold">Contra o CDI em 12 meses</h3>
          <div class="flex flex-col gap-0.5">
            <p class="text-sm">
              <span class="text-2xl font-medium tracking-[-0.01em] tabular-nums"
                >{integer(cdi.beating)} de {integer(cdi.measured)}</span
              >
              {fundCount(cdi.measured)} renderam acima do CDI
            </p>
            <p class="text-base-content/70 text-xs">
              CDI no período: <span class="tabular-nums">{percent2(cdi.cdi12m)}</span>
            </p>
          </div>
          {#if cdi.leaders.length > 0}
            <table class="table-sm table">
              <caption class="sr-only">Fundos que renderam acima do CDI em 12 meses</caption>
              <thead>
                <tr>
                  <th scope="col" class="px-0">Fundo</th>
                  <th scope="col" class="text-right" style:white-space="nowrap">% CDI</th>
                  <th scope="col" class="pr-0 text-right">Retorno</th>
                </tr>
              </thead>
              <tbody>
                {#each cdi.leaders as leader (leader.seriesId)}
                  <tr>
                    <th scope="row" class="px-0 font-normal">{@render fundLink(leader)}</th>
                    <td class="text-right whitespace-nowrap tabular-nums"
                      >{percent2(leader.pctCdi)}</td
                    >
                    <td class="pr-0 text-right whitespace-nowrap tabular-nums">
                      {percent2(leader.return12m)}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
            {#if cdi.hiddenLeaders > 0}
              <p class="text-base-content/70 grow-0 text-xs tabular-nums">
                +{integer(cdi.hiddenLeaders)}
                {fundCount(cdi.hiddenLeaders)}
              </p>
            {/if}
          {/if}
        </div>
      </article>
    {/if}

    {#if highlights.inflows}
      {@render flowCard(
        "Maiores captações em 12 meses",
        highlights.inflows,
        1,
        INFLOW_SLOT,
        "Fundos com as maiores captações líquidas em 12 meses",
      )}
    {/if}

    {#if highlights.outflows}
      {@render flowCard(
        "Maiores resgates em 12 meses",
        highlights.outflows,
        -1,
        OUTFLOW_SLOT,
        "Fundos com os maiores resgates líquidos em 12 meses",
      )}
    {/if}

    {#if highlights.creditEvent}
      {@const event = highlights.creditEvent}
      <article class="card bg-base-100 border-base-content/10 border">
        <div class="card-body gap-3 p-4 sm:p-5">
          <h3 class="text-sm font-semibold">Evento de crédito de {date(event.date)}</h3>
          <div class="flex flex-col gap-0.5">
            <p class="text-sm">
              <span class="text-2xl font-medium tracking-[-0.01em] tabular-nums"
                >{integer(event.series.length)}</span
              >
              {seriesCount(event.series.length)} caíram no mesmo dia
            </p>
            <p class="text-base-content/70 text-xs">
              Variação da cota entre <span class="tabular-nums">{percent2(event.minChange)}</span> e
              <span class="tabular-nums">{percent2(event.maxChange)}</span>, entre todas as séries
              monitoradas da gestora.
            </p>
          </div>
          <ul
            class="flex flex-col gap-1 text-sm"
            aria-label={`Séries com salto isolado em ${date(event.date)}`}
          >
            {#each event.series as entry (entry.seriesId)}
              <li class="flex items-baseline justify-between gap-3">
                <span class="min-w-0">{@render fundLink(entry)}</span>
                <span class="shrink-0 tabular-nums">{percent2(entry.change)}</span>
              </li>
            {/each}
          </ul>
          <p class="text-base-content/70 grow-0 text-xs">
            Salto isolado: fora do padrão do próprio fundo e não compartilhado pelo mercado. Ver
            Qualidade.
          </p>
        </div>
      </article>
    {/if}

    {#if highlights.incentivized}
      <article
        class="card bg-base-100 border md:col-span-2 xl:col-span-2"
        style:border-color="var(--color-warning)"
        aria-labelledby="incentivized-title"
      >
        <div class="card-body gap-3 p-4 sm:p-5">
          <div class="flex items-center gap-2">
            <svg
              class="text-warning size-5 shrink-0"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              {#each WARNING_ICON as path (path)}
                <path d={path} />
              {/each}
            </svg>
            <h3 id="incentivized-title" class="text-sm font-semibold">Fundos incentivados</h3>
          </div>
          <p class="grow-0 text-sm">
            Fundos incentivados distribuem rendimentos que o informe registra como resgate. A cota
            não é ajustada por esse evento, então o retorno pela cota subestima o que o cotista
            recebeu e a posição entre pares fica distorcida. Ver metodologia.
          </p>
          <div class="overflow-x-auto">
            <table class="table-sm table">
              <caption class="sr-only">Fundos incentivados de Público Geral</caption>
              <thead>
                <tr>
                  <th scope="col" class="px-0">Fundo</th>
                  <th scope="col" class="text-right" style:white-space="nowrap">Retorno 12m</th>
                  <th scope="col" class="pr-0 text-right">Pares</th>
                </tr>
              </thead>
              <tbody>
                {#each highlights.incentivized as fund (fund.seriesId)}
                  <tr>
                    <th scope="row" class="px-0 font-normal">{@render fundLink(fund)}</th>
                    <td class="text-right whitespace-nowrap tabular-nums"
                      >{percent2(fund.return12m)}</td
                    >
                    <td class="pr-0 text-right whitespace-nowrap tabular-nums">
                      {peerRank(fund.peerPercentile, fund.peerCount)}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      </article>
    {/if}
  </div>
</section>
