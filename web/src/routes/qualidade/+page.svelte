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
  import StatusBadge from "$lib/components/StatusBadge.svelte";
  import type { Issue, QualityEvent } from "$lib/data/types";
  import { cnpj, DASH, date, integer } from "$lib/format";
  import {
    byTriage,
    issueMagnitude,
    issueMeasure,
    issueMeasureText,
    issueSpan,
    issueText,
    RULE_DESCRIPTIONS,
    RULES,
    ruleLabel,
    triageDetail,
    triageRank,
  } from "$lib/issues";
  import {
    ALL,
    countsAsOpen,
    OPEN_SEVERITIES,
    SEVERITY_LABELS,
    severityRank,
    TREATED_STATUSES,
    untreatedInfo,
    type Severity,
  } from "$lib/labels";
  import { TABLE_LABELS } from "$lib/table";
  import type { Snapshot } from "./$types";

  const { data } = $props();

  interface Row extends Issue {
    index: number;
    text: string;
    measureText: string | null;
    triage: string;
    haystack: string;
  }

  interface RuleRow {
    rule: string;
    count: number;
  }

  type View = "open" | "treated" | "info" | typeof ALL;

  const DEFAULT_VIEW: View = "open";

  const EVENT_LIST_OPEN_LIMIT = 6;

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

  const TREATED_HINT_LABELS: Record<(typeof TREATED_STATUSES)[number], string> = {
    explained: "explicados",
    source_error: "erro da fonte",
    limitation: "limitação",
  };

  const VIEW_OPTIONS: { id: View; label: string }[] = [
    { id: "open", label: "Abertos" },
    { id: "treated", label: "Tratados" },
    { id: "info", label: "Informativos" },
    { id: ALL, label: "Todos" },
  ];

  const EMPTY_MESSAGES: Record<View, string> = {
    open: "Nenhum alerta aberto. Tudo o que o monitor achou está tratado.",
    treated: "Nenhum alerta tratado ainda.",
    info: "Nenhum alerta informativo nesta rodada.",
    all: "Nenhum alerta nesta rodada.",
  };

  const inView = (item: { status: string; severity: string }, current: View): boolean => {
    if (current === "open") return countsAsOpen(item.status, item.severity);
    if (current === "treated") return item.status !== "open";
    if (current === "info") return item.severity === "info";
    return true;
  };

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
          measureText: issueMeasureText(issue),
          triage: triageDetail(issue.note, issue.treated_on),
          haystack: normalizeForSearch(
            `${text} ${issue.display_name ?? ""} ${ruleLabel(issue.rule)} ${seriesTerms(issue.series_id)} ${issue.note ?? ""}`,
          ),
        };
      })
      .sort(byTriage),
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

  const treatedHint = $derived(
    TREATED_STATUSES.map(
      (status) => `${TREATED_HINT_LABELS[status]} ${integer(summary.by_status[status] ?? 0)}`,
    ).join(" · "),
  );

  const infoCount = $derived(summary.by_severity.info ?? 0);

  let rule = $state<string | null>(ALL);
  let view = $state<View>(DEFAULT_VIEW);
  let fund = $state<string | null>(null);
  let query = $state("");

  interface Filters {
    rule: string | null;
    view: View;
    fund: string | null;
    query: string;
  }

  export const snapshot: Snapshot<Filters> = {
    capture: () => ({ rule, view, fund, query }),
    restore: (filters) => {
      rule = filters.rule;
      view = filters.view;
      fund = filters.fund;
      query = filters.query;
    },
  };

  const needle = $derived(normalizeForSearch(query.trim()));

  const visible = $derived(
    rows.filter(
      (row) =>
        (rule === null || rule === ALL || row.rule === rule) &&
        inView(row, view) &&
        (fund === null || row.series_id === fund) &&
        (needle === "" || row.haystack.includes(needle)),
    ),
  );

  const narrowed = $derived((rule !== null && rule !== ALL) || fund !== null || needle !== "");

  const filtered = $derived(narrowed || view !== DEFAULT_VIEW);

  const eventSeries = (event: QualityEvent): { seriesId: string; name: string }[] =>
    event.series_ids
      .map((seriesId, index) => ({ seriesId, name: event.display_names[index] ?? seriesId }))
      .sort((left, right) => left.name.localeCompare(right.name, "pt-BR"));

  interface EventRow extends QualityEvent {
    key: string;
    series: { seriesId: string; name: string }[];
    haystack: string;
  }

  const eventRows = $derived<EventRow[]>(
    data.quality.events.map((event) => {
      const series = eventSeries(event);
      return {
        ...event,
        key: `${event.rule}|${event.date}`,
        series,
        haystack: normalizeForSearch(
          `${ruleLabel(event.rule)} ${event.note ?? ""} ${series
            .map((entry) => `${entry.name} ${seriesTerms(entry.seriesId)}`)
            .join(" ")}`,
        ),
      };
    }),
  );

  const visibleEvents = $derived(
    eventRows.filter(
      (event) =>
        (rule === null || rule === ALL || event.rule === rule) &&
        inView(event, view) &&
        (fund === null || event.series_ids.includes(fund)) &&
        (needle === "" || event.haystack.includes(needle)),
    ),
  );

  const clearFilters = (): void => {
    rule = ALL;
    view = DEFAULT_VIEW;
    fund = null;
    query = "";
  };

  const showInfo = (): void => {
    view = "info";
    document.getElementById("issues-title")?.scrollIntoView({ block: "start" });
  };

  const alertCount = (count: number): string =>
    `${integer(count)} ${count === 1 ? "alerta" : "alertas"}`;

  const seriesCount = (count: number): string =>
    `${integer(count)} ${count === 1 ? "série" : "séries"}`;

  const cnpjCount = (count: number): string =>
    `${integer(count)} ${count === 1 ? "CNPJ" : "CNPJs"}`;

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
      key: "status",
      label: "Situação",
      cell: statusCell,
      sortBy: triageRank,
      defaultSortDirection: "asc",
    },
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

{#snippet statusCell(row: Row)}
  {#if untreatedInfo(row.status, row.severity)}
    <span class="text-base-content/70" title="Informativo: não conta como aberto">{DASH}</span>
  {:else}
    <StatusBadge status={row.status} note={row.note} treatedOn={row.treated_on} />
  {/if}
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
    {#if measure.note !== null}
      <span class="text-base-content/70 block text-xs whitespace-nowrap tabular-nums">
        {measure.note}
      </span>
    {/if}
  {/if}
{/snippet}

{#snippet issueCard(row: Row)}
  <div class="flex flex-col gap-1.5">
    <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
      {#if !untreatedInfo(row.status, row.severity)}
        <StatusBadge status={row.status} />
      {/if}
      <SeverityBadge severity={row.severity} />
      <span class="text-sm font-medium">{ruleLabel(row.rule)}</span>
      <span class="text-base-content/70 text-xs tabular-nums">{issueSpan(row)}</span>
    </div>
    <div class="text-sm">{@render fundCell(row)}</div>
    <p class="text-sm">{row.text}</p>
    {#if row.measureText !== null}
      <p class="text-base-content/70 text-xs tabular-nums">{row.measureText}</p>
    {/if}
    {#if row.triage !== ""}
      <p class="text-base-content/70 text-xs">{row.triage}</p>
    {/if}
  </div>
{/snippet}

{#snippet noIssues()}
  <div class="flex flex-col items-center gap-2 py-8 text-center">
    <p class="text-base-content/70 text-sm">
      {narrowed ? "Nenhum alerta com esse filtro." : EMPTY_MESSAGES[view]}
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
  description={`Regras de qualidade aplicadas a ${integer(summary.checked_series)} séries e ${integer(summary.checked_days)} pares série × dia útil. Alertas marcam, não excluem: o dado segue no cálculo, exceto a linha zerada (descartada do cálculo), o informe duplicado (vale a linha CLASSES - FIF) e a série sem 12 meses (sem % do CDI e fora dos pares). Cada alerta tem uma situação: aberto é o que ainda precisa de leitura; explicado, erro da fonte e limitação do informe já foram lidos, e tratar um alerta não altera o dado. Informativos não contam como abertos.`}
  wide
>
  <section class="flex flex-col gap-2" aria-labelledby="severity-tiles-title">
    <h2 id="severity-tiles-title" class="sr-only">Alertas abertos por severidade e tratados</h2>
    <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {#each OPEN_SEVERITIES as level (level)}
        {@const count = summary.open_by_severity[level] ?? 0}
        <StatTile
          label={`Abertos · ${SEVERITY_LABELS[level]}`}
          value={integer(count)}
          hint={SEVERITY_HINTS[level]}
          tone={count === 0 ? "neutral" : SEVERITY_TONES[level]}
        />
      {/each}
      <StatTile label="Tratados" value={integer(summary.treated)} hint={treatedHint} />
    </div>
    <p class="text-base-content/70 text-xs">
      <span class="tabular-nums">{integer(infoCount)}</span>
      {infoCount === 1
        ? "informativo à parte, explicado pelo mercado ou pelo cadastro: não conta como aberto."
        : "informativos à parte, explicados pelo mercado ou pelo cadastro: não contam como abertos."}
      {#if infoCount > 0}
        <button type="button" class="link" onclick={showInfo}>Ver informativos</button>.
      {/if}
    </p>
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
          bind:value={view}
          options={VIEW_OPTIONS}
          label="Situação dos alertas exibidos"
          caption="Situação:"
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
    {#if visibleEvents.length > 0}
      <section class="flex flex-col gap-2" aria-labelledby="events-title">
        <div class="flex flex-col gap-0.5">
          <h3 id="events-title" class="text-sm font-semibold">
            Eventos
            <span class="text-base-content/70 font-normal tabular-nums">
              · {integer(visibleEvents.length)}
            </span>
          </h3>
          <p class="text-base-content/70 text-xs">
            Dias com salto de cota em 3 ou mais séries, lidos como um evento só. A situação é a de
            todos os alertas do dia; se eles divergem, o evento fica aberto. Seguem os filtros acima.
          </p>
        </div>
        <div class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {#each visibleEvents as event (event.key)}
            <article
              class="card bg-base-100 border-base-content/10 border"
              aria-labelledby={`event-${event.date}`}
            >
              <div class="card-body gap-3 p-4 sm:p-5">
                <div class="flex flex-col gap-1.5">
                  <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                    {#if event.severity === "info"}
                      <span class="badge badge-sm badge-outline shrink-0">Dia de mercado</span>
                      {#if event.status !== "open"}
                        <StatusBadge status={event.status} />
                      {/if}
                    {:else}
                      <StatusBadge status={event.status} />
                      <SeverityBadge severity={event.severity} />
                    {/if}
                  </div>
                  <h4 id={`event-${event.date}`} class="text-sm font-semibold">
                    {ruleLabel(event.rule)} em <span class="tabular-nums">{date(event.date)}</span>
                  </h4>
                </div>
                <p class="grow-0 text-sm">
                  <span class="text-2xl font-medium tracking-[-0.01em] tabular-nums"
                    >{integer(event.series.length)}</span
                  >
                  {event.series.length === 1 ? "série" : "séries"} de {cnpjCount(event.cnpj_count)}
                </p>
                {#if event.note !== null}
                  <p class="grow-0 text-sm">{event.note}</p>
                {:else if event.severity === "info"}
                  <p class="text-base-content/70 grow-0 text-xs">
                    Movimento compartilhado pelo mercado: os alertas do dia são informativos.
                  </p>
                {/if}
                <details class="grow-0 text-sm" open={event.series.length <= EVENT_LIST_OPEN_LIMIT}>
                  <summary class="text-base-content/70 cursor-pointer text-xs">
                    {seriesCount(event.series.length)} no evento
                  </summary>
                  <ul
                    class="mt-1.5 flex flex-col gap-1"
                    aria-label={`Séries do evento de ${date(event.date)}`}
                  >
                    {#each event.series as entry (entry.seriesId)}
                      <li class="min-w-0">
                        {#if linkable.has(entry.seriesId)}
                          <a
                            class="link link-hover"
                            href={resolve("/fundo/[id]", { id: entry.seriesId })}
                            title={entry.seriesId}>{entry.name}</a
                          >
                        {:else}
                          <span title={entry.seriesId}>{entry.name}</span>
                        {/if}
                      </li>
                    {/each}
                  </ul>
                </details>
              </div>
            </article>
          {/each}
        </div>
      </section>
      <h3 class="text-sm font-semibold">Alertas um a um</h3>
    {/if}
    <div class="card bg-base-100 border-base-content/10 border">
      <div class="card-body p-2 sm:p-3">
        <DataTable
          rows={visible}
          {columns}
          rowKey={(row) => row.index}
          sort={{ key: "status", direction: "asc" }}
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
