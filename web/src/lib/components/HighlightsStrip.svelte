<script lang="ts">
  import { resolve } from "$app/paths";
  import { INFLOW_SLOT, OUTFLOW_SLOT } from "$lib/charts/palette";
  import { date, integer, moneyCompact, peerRank, percent2 } from "$lib/format";
  import type { FlowHighlight, HighlightFund, Highlights } from "$lib/highlights";
  import { untreatedInfo } from "$lib/labels";
  import HorizontalBarChart, { type HorizontalBar } from "./HorizontalBarChart.svelte";
  import StatusBadge from "./StatusBadge.svelte";

  const { highlights }: { highlights: Highlights } = $props();

  const WARNING_ICON = [
    "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3",
    "M12 9v4",
    "M12 17h.01",
  ];

  const UNIVERSE_SCOPE = "Público Geral, sem veículos estruturais";

  const fundHref = (fund: HighlightFund): string | undefined =>
    fund.linked ? resolve("/fundo/[id]", { id: fund.seriesId }) : undefined;

  const flowBars = (flow: FlowHighlight): HorizontalBar[] =>
    flow.bars.map((bar) => ({
      id: bar.seriesId,
      label: bar.partial ? `${bar.name}*` : bar.name,
      value: bar.netFlow,
      href: fundHref(bar),
    }));

  const seriesCount = (count: number): string => (count === 1 ? "série" : "séries");

  const fundCount = (count: number): string => (count === 1 ? "fundo" : "fundos");
</script>

{#snippet fundLink(fund: HighlightFund)}
  {@const href = fundHref(fund)}
  {#if href === undefined}
    <span>{fund.name}</span>
  {:else}
    <a class="link link-hover" {href}>{fund.name}</a>
  {/if}
{/snippet}

{#snippet cardTitle(title: string, scope: string, id?: string)}
  <div class="flex flex-col gap-0.5">
    <h3 {id} class="text-sm font-semibold">{title}</h3>
    <p class="text-base-content/70 text-xs">{scope}</p>
  </div>
{/snippet}

{#snippet flowCard(title: string, flow: FlowHighlight, slot: number, label: string)}
  <article class="card bg-base-100 border-base-content/10 border">
    <div class="card-body gap-3 p-4 sm:p-5">
      {@render cardTitle(title, `${UNIVERSE_SCOPE}.`)}
      <HorizontalBarChart rows={flowBars(flow)} formatValue={moneyCompact} ariaLabel={label} {slot} />
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
      Dados até {date(highlights.asOf)}. Cada cartão diz o próprio recorte, e nenhum segue os filtros
      da página.
    </p>
  </div>

  <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
    {#if highlights.cdi}
      {@const cdi = highlights.cdi}
      <article class="card bg-base-100 border-base-content/10 border">
        <div class="card-body gap-3 p-4 sm:p-5">
          {@render cardTitle("Contra o CDI em 12 meses", `${UNIVERSE_SCOPE}.`)}
          <div class="flex flex-col gap-0.5">
            <p class="text-sm">
              <span class="text-2xl font-medium tracking-[-0.01em] tabular-nums"
                >{integer(cdi.beating)} de {integer(cdi.measured)}</span
              >
              {seriesCount(cdi.measured)} renderam acima do CDI
            </p>
            {#if cdi.cdi12m !== null}
              <p class="text-base-content/70 text-xs">
                CDI no período: <span class="tabular-nums">{percent2(cdi.cdi12m)}</span>
              </p>
            {/if}
          </div>
          {#if cdi.leaders.length > 0}
            <table class="table-sm table">
              <caption class="sr-only">Séries que renderam acima do CDI em 12 meses</caption>
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
                {seriesCount(cdi.hiddenLeaders)}
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
        INFLOW_SLOT,
        "Séries com as maiores captações líquidas em 12 meses",
      )}
    {/if}

    {#if highlights.outflows}
      {@render flowCard(
        "Maiores resgates em 12 meses",
        highlights.outflows,
        OUTFLOW_SLOT,
        "Séries com os maiores resgates líquidos em 12 meses",
      )}
    {/if}

    {#if highlights.creditEvent}
      {@const event = highlights.creditEvent}
      <article class="card bg-base-100 border-base-content/10 border">
        <div class="card-body gap-3 p-4 sm:p-5">
          {@render cardTitle(
            `Evento de crédito de ${date(event.date)}`,
            `Todas as séries monitoradas da gestora, desde ${date(event.windowStart)}.`,
          )}
          <div class="flex flex-col gap-0.5">
            <p class="text-sm">
              <span class="text-2xl font-medium tracking-[-0.01em] tabular-nums"
                >{integer(event.cnpjCount)}</span
              >
              {fundCount(event.cnpjCount)}
              <span class="tabular-nums"
                >({integer(event.series.length)} {seriesCount(event.series.length)})</span
              >
              caíram no mesmo dia
            </p>
            {#if event.cnpjCount < event.series.length}
              <p class="text-base-content/70 text-xs">
                Subclasses criadas depois do evento herdam a cota da classe, e a mesma queda aparece em
                mais de uma série.
              </p>
            {/if}
            <p class="text-base-content/70 text-xs">
              Variação da cota entre <span class="tabular-nums">{percent2(event.minChange)}</span> e
              <span class="tabular-nums">{percent2(event.maxChange)}</span>.
            </p>
          </div>
          {#if event.triage !== null && !untreatedInfo(event.triage.status, event.triage.severity)}
            <div class="flex flex-col gap-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-base-content/70 text-xs">Situação:</span>
                <StatusBadge status={event.triage.status} />
              </div>
              {#if event.triage.note !== null}
                <p class="text-sm">{event.triage.note}</p>
              {/if}
            </div>
          {/if}
          <ul
            class="flex flex-col gap-1 text-sm"
            aria-label={`Séries com queda isolada em ${date(event.date)}`}
          >
            {#each event.series as entry (entry.seriesId)}
              <li class="flex items-baseline justify-between gap-3">
                <span class="min-w-0">{@render fundLink(entry)}</span>
                <span class="shrink-0 tabular-nums">{percent2(entry.change)}</span>
              </li>
            {/each}
          </ul>
          <p class="text-base-content/70 grow-0 text-xs">
            Queda isolada: fora do padrão da própria série e não compartilhada pelo mercado.
            <a class="link" href={resolve("/qualidade")}>Ver qualidade</a>.
          </p>
        </div>
      </article>
    {/if}

    {#if highlights.incentivized}
      <article
        class="card bg-base-100 border self-start md:col-span-2"
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
            {@render cardTitle("Fundos incentivados", `${UNIVERSE_SCOPE}.`, "incentivized-title")}
          </div>
          <p class="grow-0 text-sm">
            Fundos incentivados pagam rendimentos que o informe parece registrar como resgate,
            leitura ainda a confirmar. A cota não é ajustada por esse evento, então o retorno pela
            cota subestima o que o cotista recebeu e a posição entre pares fica distorcida.
            <a class="link" href={resolve("/como-funciona")}>Ver como funciona</a>.
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
