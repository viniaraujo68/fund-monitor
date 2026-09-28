<script lang="ts">
  import { resolve } from "$app/paths";
  import {
    Combobox,
    normalizeForSearch,
    SegmentedControl,
    Select,
    type SelectOption,
  } from "@viniaraujo68/plinth/components";
  import { DataTable, type Column } from "@viniaraujo68/plinth/table";
  import PageFrame from "$lib/components/PageFrame.svelte";
  import SeverityBadge from "$lib/components/SeverityBadge.svelte";
  import SourceDates from "$lib/components/SourceDates.svelte";
  import StatTile from "$lib/components/StatTile.svelte";
  import type { Issue } from "$lib/data/types";
  import { cnpj, DASH, integer } from "$lib/format";
  import {
    issueMagnitude,
    issueMeasure,
    issueSpan,
    issueText,
    RULE_DESCRIPTIONS,
    RULES,
    ruleLabel,
  } from "$lib/issues";
  import { ALL, SEVERITIES, SEVERITY_LABELS, severityRank, type Severity } from "$lib/labels";
  import { TABLE_LABELS } from "$lib/table";
  import type { Snapshot } from "./$types";

  const { data } = $props();

  interface Row extends Issue {
    index: number;
    text: string;
    haystack: string;
  }

  interface RuleRow {
    rule: string;
    count: number;
  }

  type SeverityFilter = Severity | typeof ALL;

  const SEVERITY_HINTS: Record<Severity, string> = {
    high: "linha zerada (descartada do cálculo) ou fonte muito atrasada",
    medium: "provável erro ou evento a explicar",
    low: "lacuna pequena",
    info: "explicado pelo mercado ou pelo cadastro",
  };

  const SEVERITY_TONES: Record<Severity, "negative" | "attention" | "neutral"> = {
    high: "negative",
    medium: "attention",
    low: "neutral",
    info: "neutral",
  };

  const SEVERITY_OPTIONS: { id: SeverityFilter; label: string }[] = [
    { id: ALL, label: "Todas" },
    ...SEVERITIES.map((level) => ({ id: level, label: SEVERITY_LABELS[level] })),
  ];

  const RULE_OPTIONS: SelectOption[] = [
    { value: ALL, label: "Todas" },
    ...RULES.map((rule) => ({ value: rule, label: ruleLabel(rule) })),
  ];

  const seriesTerms = (seriesId: string | null): string => {
    if (seriesId === null) return "";
    const classCnpj = seriesId.split("-")[0] ?? seriesId;
    return `${seriesId} ${cnpj(classCnpj)}`;
  };

  const summary = $derived(data.quality.summary);
  const linkable = $derived(new Set(data.fundIds));

  const rows = $derived<Row[]>(
    data.quality.issues
      .map((issue, index) => {
        const text = issueText(issue);
        return {
          ...issue,
          index,
          text,
          haystack: normalizeForSearch(
            `${text} ${issue.display_name ?? ""} ${ruleLabel(issue.rule)} ${seriesTerms(issue.series_id)}`,
          ),
        };
      })
      .sort((left, right) => (right.date ?? "").localeCompare(left.date ?? "")),
  );

  const fundOptions = $derived<SelectOption[]>(
    [
      ...new Map(
        data.quality.issues
          .filter((issue) => issue.series_id !== null)
          .map((issue) => [issue.series_id ?? "", issue.display_name ?? issue.series_id ?? ""]),
      ),
    ]
      .map(([value, label]) => ({ value, label }))
      .sort((left, right) => left.label.localeCompare(right.label, "pt-BR")),
  );

  const ruleRows = $derived<RuleRow[]>(
    RULES.map((rule) => ({ rule, count: summary.by_rule[rule] ?? 0 })),
  );

  let rule = $state<string | null>(ALL);
  let severity = $state<SeverityFilter>(ALL);
  let fund = $state<string | null>(null);
  let query = $state("");

  interface Filters {
    rule: string | null;
    severity: SeverityFilter;
    fund: string | null;
    query: string;
  }

  export const snapshot: Snapshot<Filters> = {
    capture: () => ({ rule, severity, fund, query }),
    restore: (filters) => {
      rule = filters.rule;
      severity = filters.severity;
      fund = filters.fund;
      query = filters.query;
    },
  };

  const needle = $derived(normalizeForSearch(query.trim()));

  const visible = $derived(
    rows.filter(
      (row) =>
        (rule === null || rule === ALL || row.rule === rule) &&
        (severity === ALL || row.severity === severity) &&
        (fund === null || row.series_id === fund) &&
        (needle === "" || row.haystack.includes(needle)),
    ),
  );

  const filtered = $derived(
    (rule !== null && rule !== ALL) || severity !== ALL || fund !== null || needle !== "",
  );

  const clearFilters = (): void => {
    rule = ALL;
    severity = ALL;
    fund = null;
    query = "";
  };

  const alertCount = (count: number): string =>
    `${integer(count)} ${count === 1 ? "alerta" : "alertas"}`;

  const ruleColumns: Column<RuleRow>[] = [
    {
      key: "rule",
      label: "Regra",
      value: (row) => ruleLabel(row.rule),
      class: "font-medium whitespace-nowrap",
    },
    {
      key: "detects",
      label: "O que detecta",
      value: (row) => RULE_DESCRIPTIONS[row.rule]?.detects ?? DASH,
      sortable: false,
    },
    {
      key: "threshold",
      label: "Limiar",
      value: (row) => RULE_DESCRIPTIONS[row.rule]?.threshold ?? DASH,
      sortable: false,
    },
    {
      key: "count",
      label: "Alertas",
      numeric: true,
      value: (row) => integer(row.count),
      sortBy: (row) => row.count,
    },
    {
      key: "severity",
      label: "Severidade típica",
      value: (row) => RULE_DESCRIPTIONS[row.rule]?.severity ?? DASH,
      sortable: false,
    },
  ];

  const columns: Column<Row>[] = [
    {
      key: "severity",
      label: "Severidade",
      cell: severityCell,
      sortBy: (row) => severityRank(row.severity),
      defaultSortDirection: "asc",
    },
    {
      key: "rule",
      label: "Regra",
      class: "whitespace-nowrap",
      value: (row) => ruleLabel(row.rule),
    },
    {
      key: "fund",
      label: "Fundo",
      cell: fundCell,
      sortBy: (row) => row.display_name ?? row.series_id,
    },
    {
      key: "date",
      label: "Data",
      class: "whitespace-nowrap tabular-nums",
      value: issueSpan,
      sortBy: (row) => row.date,
      defaultSortDirection: "desc",
    },
    {
      key: "text",
      label: "Descrição",
      sortable: false,
    },
    {
      key: "measure",
      label: "Valor / limiar",
      numeric: true,
      cell: measureCell,
      sortBy: issueMagnitude,
    },
  ];
</script>

{#snippet ruleCard(row: RuleRow)}
  {@const description = RULE_DESCRIPTIONS[row.rule]}
  <div class="flex flex-col gap-1">
    <div class="flex items-baseline justify-between gap-3">
      <span class="text-sm font-medium">{ruleLabel(row.rule)}</span>
      <span class="text-sm tabular-nums">{alertCount(row.count)}</span>
    </div>
    {#if description !== undefined}
      <p class="text-sm">{description.detects}</p>
      <p class="text-base-content/70 text-xs">
        Limiar: {description.threshold} · Severidade: {description.severity}
      </p>
    {/if}
  </div>
{/snippet}

{#snippet severityCell(row: Row)}
  <SeverityBadge severity={row.severity} />
{/snippet}

{#snippet fundCell(row: Row)}
  {#if row.series_id === null}
    <span class="text-base-content/70">{DASH}</span>
  {:else if linkable.has(row.series_id)}
    <a
      class="link link-hover font-medium"
      href={resolve("/fundo/[id]", { id: row.series_id })}
      title={row.series_id}
    >
      {row.display_name ?? row.series_id}
    </a>
  {:else}
    <span title={row.series_id}>{row.display_name ?? row.series_id}</span>
  {/if}
{/snippet}

{#snippet measureCell(row: Row)}
  {@const measure = issueMeasure(row)}
  {#if measure === null}
    <span class="text-base-content/70">{DASH}</span>
  {:else}
    <span class="block whitespace-nowrap tabular-nums">{measure.value}</span>
    {#if measure.limit !== null}
      <span class="text-base-content/70 block text-xs whitespace-nowrap tabular-nums">
        {measure.limit}
      </span>
    {/if}
  {/if}
{/snippet}

{#snippet issueCard(row: Row)}
  <div class="flex flex-col gap-1.5">
    <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
      <SeverityBadge severity={row.severity} />
      <span class="text-sm font-medium">{ruleLabel(row.rule)}</span>
      <span class="text-base-content/70 text-xs tabular-nums">{issueSpan(row)}</span>
    </div>
    <div class="text-sm">{@render fundCell(row)}</div>
    <p class="text-sm">{row.text}</p>
  </div>
{/snippet}

{#snippet noIssues()}
  <div class="flex flex-col items-center gap-2 py-8 text-center">
    <p class="text-base-content/70 text-sm">
      {filtered ? "Nenhum alerta com esse filtro." : "Nenhum alerta nesta rodada."}
    </p>
    {#if filtered}
      <button type="button" class="btn btn-ghost btn-sm" onclick={clearFilters}>
        Limpar filtros
      </button>
    {/if}
  </div>
{/snippet}

<PageFrame
  title="Qualidade"
  description={`Regras de qualidade aplicadas a ${integer(summary.checked_series)} séries e ${integer(summary.checked_days)} pares série × dia útil. Alertas marcam, não excluem: o dado segue no cálculo. As exceções são a linha zerada (descartada do cálculo), o informe duplicado (vale a linha CLASSES - FIF) e a série sem 12 meses (sem % do CDI e fora dos pares).`}
  wide
>
  <section class="flex flex-col gap-2" aria-labelledby="severity-tiles-title">
    <h2 id="severity-tiles-title" class="sr-only">Alertas por severidade</h2>
    <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {#each SEVERITIES as level (level)}
        {@const count = summary.by_severity[level] ?? 0}
        <StatTile
          label={SEVERITY_LABELS[level]}
          value={integer(count)}
          hint={SEVERITY_HINTS[level]}
          tone={count === 0 ? "neutral" : SEVERITY_TONES[level]}
        />
      {/each}
    </div>
  </section>

  <section class="flex flex-col gap-2" aria-labelledby="rules-title">
    <div class="flex flex-col gap-0.5">
      <h2 id="rules-title" class="text-base font-semibold">Alertas por regra</h2>
      <p class="text-base-content/70 text-xs">
        Regras sem ocorrência hoje aparecem com zero: elas rodam em todo processamento.
      </p>
    </div>
    <div class="card bg-base-100 border-base-content/10 border">
      <div class="card-body p-2 sm:p-3">
        <DataTable
          rows={ruleRows}
          columns={ruleColumns}
          rowKey={(row) => row.rule}
          sort={{ key: "count", direction: "desc" }}
          label="Alertas por regra"
          class="table-sm"
          card={ruleCard}
          {...TABLE_LABELS}
        />
      </div>
    </div>
  </section>

  <section class="flex flex-col gap-2" aria-labelledby="issues-title">
    <h2 id="issues-title" class="text-base font-semibold">Alertas</h2>
    <section class="card bg-base-100 border-base-content/10 border" aria-label="Filtros dos alertas">
      <div class="card-body flex-row flex-wrap items-center gap-x-6 gap-y-3 p-4">
        <div class="flex items-center gap-2">
          <span id="rule-filter-label" class="text-sm">Regra:</span>
          <Select
            bind:value={rule}
            options={RULE_OPTIONS}
            aria-labelledby="rule-filter-label"
            class="w-48"
          />
        </div>
        <SegmentedControl
          bind:value={severity}
          options={SEVERITY_OPTIONS}
          label="Severidade dos alertas exibidos"
          caption="Severidade:"
          size="sm"
        />
        <div class="flex items-center gap-2">
          <span id="fund-filter-label" class="text-sm">Fundo:</span>
          <Combobox
            bind:value={fund}
            options={fundOptions}
            aria-labelledby="fund-filter-label"
            placeholder="Todos"
            emptyLabel="Nenhum fundo encontrado"
            clearLabel="Mostrar todos os fundos"
            clearable
            class="w-64 max-w-full"
          />
        </div>
        <label class="input input-sm w-64 max-w-full">
          <span class="sr-only">Buscar no texto dos alertas, no nome ou no CNPJ da série</span>
          <input type="search" bind:value={query} placeholder="Buscar no texto ou CNPJ" />
        </label>
        <div class="flex items-center gap-3 sm:ml-auto">
          <span class="text-sm font-medium tabular-nums" aria-live="polite">
            {alertCount(visible.length)}
          </span>
          {#if filtered}
            <button type="button" class="btn btn-ghost btn-sm" onclick={clearFilters}>
              Limpar filtros
            </button>
          {/if}
        </div>
      </div>
    </section>
    <div class="card bg-base-100 border-base-content/10 border">
      <div class="card-body p-2 sm:p-3">
        <DataTable
          rows={visible}
          {columns}
          rowKey={(row) => row.index}
          sort={{ key: "severity", direction: "asc" }}
          label="Alertas de qualidade"
          class="table-sm"
          card={issueCard}
          empty={noIssues}
          {...TABLE_LABELS}
        />
      </div>
    </div>
  </section>

  <div class="text-base-content/70 flex flex-col gap-1 text-xs sm:flex-row sm:flex-wrap sm:gap-x-2">
    <span>Fontes e última data:</span>
    <SourceDates sources={data.meta.sources} />
  </div>
</PageFrame>
