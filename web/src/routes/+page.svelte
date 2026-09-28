<script lang="ts">
  import { resolve } from "$app/paths";
  import { Select, SegmentedControl } from "@viniaraujo68/plinth/components";
  import { DataTable, type Column } from "@viniaraujo68/plinth/table";
  import { classificationSlot } from "$lib/charts/palette";
  import BarChart, { type BarSeries } from "$lib/components/BarChart.svelte";
  import ChartCard from "$lib/components/ChartCard.svelte";
  import HighlightsStrip from "$lib/components/HighlightsStrip.svelte";
  import PageFrame from "$lib/components/PageFrame.svelte";
  import QualityStrip from "$lib/components/QualityStrip.svelte";
  import StatTile from "$lib/components/StatTile.svelte";
  import type { FundSummary } from "$lib/data/types";
  import { isPartialMonth, MIN_PEERS } from "$lib/fund";
  import {
    DASH,
    date,
    integer,
    money,
    moneyCompact,
    monthLabel,
    peerRank,
    percent2,
    ratio2,
  } from "$lib/format";
  import {
    ALL,
    AUDIENCES,
    CLASSIFICATIONS,
    GENERAL_PUBLIC,
    SEVERITIES,
    severityCountWord,
  } from "$lib/labels";
  import { TABLE_LABELS } from "$lib/table";
  import type { Snapshot } from "./$types";

  const { data } = $props();

  const CHART_MONTHS = 12;

  type Audience = (typeof AUDIENCES)[number] | typeof ALL;
  type Scope = "monitored" | "manager";

  const AUDIENCE_OPTIONS: { id: Audience; label: string }[] = [
    ...AUDIENCES.map((audience) => ({ id: audience, label: audience })),
    { id: ALL, label: "Todos" },
  ];

  const CLASSIFICATION_OPTIONS = [
    { value: ALL, label: "Todas" },
    ...CLASSIFICATIONS.map((classification) => ({ value: classification, label: classification })),
  ];

  interface Filters {
    audience: Audience;
    includeStructural: boolean;
    includeExclusive: boolean;
    classification: string | null;
  }

  let audience = $state<Audience>(GENERAL_PUBLIC);
  let includeStructural = $state(false);
  let includeExclusive = $state(false);
  let classification = $state<string | null>(ALL);

  export const snapshot: Snapshot<Filters> = {
    capture: () => ({ audience, includeStructural, includeExclusive, classification }),
    restore: (filters) => {
      audience = filters.audience;
      includeStructural = filters.includeStructural;
      includeExclusive = filters.includeExclusive;
      classification = filters.classification;
    },
  };

  const scope = $derived<Scope>(includeExclusive ? "manager" : "monitored");

  const visible = $derived(
    data.funds.filter(
      (fund) =>
        (audience === ALL || fund.target_audience === audience) &&
        (includeStructural || !fund.structural_vehicle) &&
        (classification === null ||
          classification === ALL ||
          fund.cvm_classification === classification),
    ),
  );

  const sumOf = (rows: FundSummary[], pick: (fund: FundSummary) => number | null): number =>
    rows.reduce((total, fund) => total + (pick(fund) ?? 0), 0);

  const visibleNetAssets = $derived(sumOf(visible, (fund) => fund.net_assets));
  const visibleNetFlow = $derived(sumOf(visible, (fund) => fund.net_flow_12m));
  const partialFlows = $derived(visible.filter((fund) => fund.flow_window_partial === true).length);

  const seriesCount = (count: number): string =>
    `${integer(count)} ${count === 1 ? "série" : "séries"}`;

  const visibleHint = $derived(
    partialFlows === 0
      ? seriesCount(visible.length)
      : `${seriesCount(visible.length)} · captação com janela parcial em ${seriesCount(partialFlows)}`,
  );

  const total = $derived(data.totals.find((row) => row.scope === scope));

  const managerHint = $derived(
    total === undefined
      ? undefined
      : `${integer(total.classes)} ${total.classes === 1 ? "classe" : "classes"} · ${
          includeExclusive ? "inclusive exclusivas" : "não exclusivas"
        }`,
  );

  const months = $derived.by(() => {
    const all = [
      ...new Set(data.monthly.filter((row) => row.scope === scope).map((row) => row.month)),
    ].sort();
    return all.slice(-CHART_MONTHS);
  });

  const flowByMonth = $derived.by(() => {
    const table = new Map<string, number>();
    for (const row of data.monthly) {
      if (row.scope !== scope || row.group_value === null) continue;
      table.set(`${row.month}|${row.group_value}`, row.net_flow);
    }
    return table;
  });

  const flowAt = (month: string, group: string): number | null =>
    flowByMonth.get(`${month}|${group}`) ?? null;

  const flowSeries = $derived<BarSeries[]>(
    CLASSIFICATIONS.map((group) => ({
      label: group,
      slot: classificationSlot(group),
      data: months.map((month) => flowAt(month, group)),
    })),
  );

  const monthTotal = (month: string): number =>
    CLASSIFICATIONS.reduce((sum, group) => sum + (flowAt(month, group) ?? 0), 0);

  const lastMonth = $derived(months.at(-1));
  const partialMonth = $derived(
    lastMonth !== undefined && isPartialMonth(lastMonth, data.meta.as_of),
  );

  const flowNote = $derived(
    [
      includeExclusive
        ? "Todas as séries da gestora, inclusive exclusivas."
        : "Séries não exclusivas da gestora.",
      "Não segue os filtros de público, classificação e veículos estruturais.",
      partialMonth && lastMonth !== undefined
        ? `${monthLabel(lastMonth)} parcial, até ${date(data.meta.as_of)}.`
        : null,
    ]
      .filter((part) => part !== null)
      .join(" "),
  );

  const alertRank = (fund: FundSummary): number | null =>
    fund.issues.high + fund.issues.medium === 0
      ? null
      : fund.issues.high * 1000 + fund.issues.medium;

  const alertTitle = (fund: FundSummary): string =>
    SEVERITIES.map(
      (level) => `${integer(fund.issues[level])} ${severityCountWord(level, fund.issues[level])}`,
    ).join(", ");

  const columns: Column<FundSummary>[] = [
    {
      key: "display_name",
      label: "Nome",
      hideable: false,
      cell: nameCell,
      sortBy: (fund) => fund.display_name,
    },
    {
      key: "cvm_classification",
      label: "Classificação",
      value: (fund) => fund.cvm_classification ?? DASH,
      sortBy: (fund) => fund.cvm_classification,
    },
    {
      key: "anbima_classification",
      label: "ANBIMA",
      hiddenByDefault: true,
      value: (fund) => fund.anbima_classification ?? DASH,
      sortBy: (fund) => fund.anbima_classification,
    },
    {
      key: "target_audience",
      label: "Público",
      hiddenByDefault: true,
      class: "whitespace-nowrap",
      value: (fund) => fund.target_audience ?? DASH,
      sortBy: (fund) => fund.target_audience,
    },
    {
      key: "return_12m",
      label: "Retorno 12m",
      numeric: true,
      class: "whitespace-nowrap",
      value: (fund) => percent2(fund.return_12m),
      sortBy: (fund) => fund.return_12m,
    },
    {
      key: "pct_cdi_12m",
      label: "% CDI 12m",
      numeric: true,
      class: "whitespace-nowrap",
      value: (fund) => percent2(fund.pct_cdi_12m),
      sortBy: (fund) => fund.pct_cdi_12m,
    },
    {
      key: "volatility_12m",
      label: "Vol. 12m",
      numeric: true,
      class: "whitespace-nowrap",
      value: (fund) => percent2(fund.volatility_12m),
      sortBy: (fund) => fund.volatility_12m,
    },
    {
      key: "max_drawdown_12m",
      label: "Drawdown 12m",
      numeric: true,
      class: "whitespace-nowrap",
      value: (fund) => percent2(fund.max_drawdown_12m),
      sortBy: (fund) => fund.max_drawdown_12m,
    },
    {
      key: "sharpe_12m",
      label: "Sharpe 12m",
      numeric: true,
      class: "whitespace-nowrap",
      value: (fund) => ratio2(fund.sharpe_12m),
      sortBy: (fund) => fund.sharpe_12m,
    },
    {
      key: "net_assets",
      label: "PL",
      numeric: true,
      class: "whitespace-nowrap",
      cell: netAssetsCell,
      sortBy: (fund) => fund.net_assets,
    },
    {
      key: "net_flow_12m",
      label: "Captação 12m",
      numeric: true,
      class: "whitespace-nowrap",
      cell: netFlowCell,
      sortBy: (fund) => fund.net_flow_12m,
    },
    {
      key: "shareholders",
      label: "Cotistas",
      numeric: true,
      class: "whitespace-nowrap",
      value: (fund) => integer(fund.shareholders),
      sortBy: (fund) => fund.shareholders,
    },
    {
      key: "peers",
      label: "Pares",
      numeric: true,
      class: "whitespace-nowrap",
      value: (fund) => peerRank(fund.peer_return_percentile_12m, fund.peer_count),
      sortBy: (fund) => fund.peer_return_percentile_12m,
    },
    {
      key: "issues",
      label: "Alertas",
      numeric: true,
      class: "whitespace-nowrap",
      cell: alertsCell,
      sortBy: alertRank,
    },
  ];
</script>

{#snippet nameCell(fund: FundSummary)}
  <span class="inline-flex min-w-0 flex-wrap items-center gap-1.5">
    <a
      class="link link-hover font-medium"
      href={resolve("/fundo/[id]", { id: fund.series_id })}
      title={fund.class_name}
    >
      {fund.display_name}
    </a>
    {#if fund.structural_vehicle}
      <span class="badge badge-outline badge-xs">estrutural</span>
    {/if}
  </span>
{/snippet}

{#snippet netAssetsCell(fund: FundSummary)}
  <span title={money(fund.net_assets)}>{moneyCompact(fund.net_assets)}</span>
{/snippet}

{#snippet netFlowCell(fund: FundSummary)}
  <span title={money(fund.net_flow_12m)}>
    {moneyCompact(fund.net_flow_12m)}{#if fund.flow_window_partial === true}<span
        class="text-base-content/70"
        title="Janela parcial: a série tem menos de 12 meses de captação"
        >*</span
      >{/if}
  </span>
{/snippet}

{#snippet alertsCell(fund: FundSummary)}
  {#if fund.issues.high + fund.issues.medium === 0}
    <span class="text-base-content/70">{DASH}</span>
  {:else}
    <span class="inline-flex flex-wrap justify-end gap-1" title={alertTitle(fund)}>
      {#if fund.issues.high > 0}
        <span class="badge badge-error badge-sm tabular-nums">
          {integer(fund.issues.high)}
          {severityCountWord("high", fund.issues.high)}
        </span>
      {/if}
      {#if fund.issues.medium > 0}
        <span class="badge badge-warning badge-sm tabular-nums">
          {integer(fund.issues.medium)}
          {severityCountWord("medium", fund.issues.medium)}
        </span>
      {/if}
    </span>
  {/if}
{/snippet}

{#snippet fundCard(fund: FundSummary)}
  <div class="flex flex-col gap-2">
    <div class="flex flex-col gap-0.5">
      {@render nameCell(fund)}
      <span class="text-base-content/70 text-xs">
        {fund.cvm_classification ?? DASH} · {fund.target_audience ?? DASH}
      </span>
    </div>
    <dl class="grid grid-cols-3 gap-2 text-sm">
      <div class="flex flex-col">
        <dt class="text-base-content/70 text-xs">Retorno 12m</dt>
        <dd class="tabular-nums">{percent2(fund.return_12m)}</dd>
      </div>
      <div class="flex flex-col">
        <dt class="text-base-content/70 text-xs">% CDI 12m</dt>
        <dd class="tabular-nums">{percent2(fund.pct_cdi_12m)}</dd>
      </div>
      <div class="flex flex-col">
        <dt class="text-base-content/70 text-xs">PL</dt>
        <dd class="tabular-nums">{moneyCompact(fund.net_assets)}</dd>
      </div>
    </dl>
  </div>
{/snippet}

{#snippet noFunds()}
  <p class="text-base-content/70 py-8 text-center text-sm">Nenhum fundo com esse filtro.</p>
{/snippet}

<PageFrame
  title="Visão geral"
  description={`Fundos da ${data.meta.manager_name}`}
  breadcrumbs={false}
  wide
>
  <QualityStrip meta={data.meta} />

  <HighlightsStrip highlights={data.highlights} />

  <section
    class="card bg-base-100 border-base-content/10 border"
    aria-label="Filtros dos fundos exibidos"
  >
    <div class="card-body flex-row flex-wrap items-center gap-x-6 gap-y-3 p-4">
      <SegmentedControl
        bind:value={audience}
        options={AUDIENCE_OPTIONS}
        label="Público-alvo dos fundos exibidos"
        caption="Público:"
        size="sm"
      />
      <div class="flex items-center gap-2">
        <span id="classification-label" class="text-sm">Classificação:</span>
        <Select
          bind:value={classification}
          options={CLASSIFICATION_OPTIONS}
          aria-labelledby="classification-label"
          class="w-44"
        />
      </div>
      <label class="flex cursor-pointer items-center gap-2 text-sm">
        <input type="checkbox" class="toggle toggle-sm" bind:checked={includeStructural} />
        Incluir veículos estruturais
      </label>
    </div>
  </section>

  <section class="flex flex-col gap-2" aria-labelledby="visible-tiles-title">
    <h2 id="visible-tiles-title" class="text-sm font-semibold">Dos fundos exibidos</h2>
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <StatTile
        label="Patrimônio líquido"
        value={moneyCompact(visibleNetAssets)}
        detail={money(visibleNetAssets)}
        hint={seriesCount(visible.length)}
      />
      <StatTile
        label="Captação líquida em 12 meses"
        value={moneyCompact(visibleNetFlow)}
        detail={money(visibleNetFlow)}
        hint={visibleHint}
      />
    </div>
  </section>

  <section class="flex flex-col gap-2" aria-labelledby="manager-tiles-title">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 id="manager-tiles-title" class="text-sm font-semibold">Da gestora</h2>
      <div class="flex flex-wrap items-center gap-2">
        {#if includeExclusive}
          <span class="text-base-content/70 text-xs">
            inclui as {integer(data.meta.universe.exclusive_series)} séries exclusivas
          </span>
        {/if}
        <label class="flex cursor-pointer items-center gap-2 text-sm">
          <input type="checkbox" class="toggle toggle-sm" bind:checked={includeExclusive} />
          Incluir exclusivos
        </label>
      </div>
    </div>
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <StatTile
        label="Patrimônio líquido"
        value={moneyCompact(total?.net_assets)}
        detail={money(total?.net_assets)}
        hint={managerHint}
      />
      <StatTile
        label="Captação líquida em 12 meses"
        value={moneyCompact(total?.net_flow_12m)}
        detail={money(total?.net_flow_12m)}
        hint={managerHint}
      />
    </div>
  </section>

  <ChartCard title="Captação líquida mensal por classificação" note={flowNote}>
    {#snippet chart()}
      <BarChart
        labels={months.map(monthLabel)}
        series={flowSeries}
        formatValue={money}
        formatAxis={moneyCompact}
        ariaLabel={`Captação líquida mensal por classificação CVM, ${months.length} meses`}
      />
    {/snippet}
    {#snippet table()}
      <table class="table-sm table">
        <caption class="sr-only">Captação líquida mensal por classificação CVM</caption>
        <thead>
          <tr>
            <th scope="col">Mês</th>
            {#each CLASSIFICATIONS as group (group)}
              <th scope="col" class="text-right">{group}</th>
            {/each}
            <th scope="col" class="text-right">Total</th>
          </tr>
        </thead>
        <tbody>
          {#each months as month (month)}
            <tr>
              <th scope="row" class="font-normal">{monthLabel(month)}</th>
              {#each CLASSIFICATIONS as group (group)}
                <td class="text-right tabular-nums">{money(flowAt(month, group))}</td>
              {/each}
              <td class="text-right font-medium tabular-nums">{money(monthTotal(month))}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/snippet}
  </ChartCard>

  <section class="flex flex-col gap-2" aria-labelledby="funds-table-title">
    <div class="flex flex-col gap-0.5">
      <h2 id="funds-table-title" class="text-base font-semibold">Fundos</h2>
      <p class="text-base-content/70 text-xs">
        Janela de 12 meses até {date(data.meta.as_of)}. Pares: percentil do retorno 12m entre fundos
        de Público Geral da mesma classificação ANBIMA, com pelo menos {MIN_PEERS} pares; os outros públicos
        não têm pares. * captação com janela parcial.
      </p>
    </div>
    <div class="card bg-base-100 border-base-content/10 border">
      <div class="card-body p-2 sm:p-3">
        <DataTable
          rows={visible}
          {columns}
          rowKey={(fund) => fund.series_id}
          sort={{ key: "net_assets", direction: "desc" }}
          label="Resumo dos fundos"
          class="table-sm"
          card={fundCard}
          empty={noFunds}
          {...TABLE_LABELS}
        />
      </div>
    </div>
  </section>

  <p class="text-base-content/70 text-xs">
    Fonte: CVM (cadastro e informe diário), Bacen SGS, ANBIMA, B3. Séries não exclusivas da gestora;
    <a class="link" href={resolve("/metodologia")}>ver metodologia</a>.
  </p>
</PageFrame>
