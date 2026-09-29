<script lang="ts">
  import { resolve } from "$app/paths";
  import type { Meta } from "$lib/data/types";
  import { date, datetime, integer } from "$lib/format";
  import { OPEN_SEVERITIES, SEVERITY_BADGE_CLASS, severityCountWord } from "$lib/labels";
  import SourceDates from "./SourceDates.svelte";

  const { meta }: { meta: Meta } = $props();

  const openCounts = $derived(
    OPEN_SEVERITIES.map((severity) => ({
      severity,
      count: meta.quality.open_by_severity[severity] ?? 0,
    })),
  );

  const infoCount = $derived(meta.quality.by_severity.info ?? 0);

  const treatedLine = $derived(
    `${integer(meta.quality.treated)} ${meta.quality.treated === 1 ? "tratado" : "tratados"} · ${integer(infoCount)} ${severityCountWord("info", infoCount)}`,
  );
</script>

<section aria-labelledby="quality-strip-title">
  <a
    href={resolve("/qualidade")}
    aria-label="Qualidade dos dados: ver alertas"
    class="card bg-base-100 border-base-content/10 hover:border-base-content/30 focus-visible:outline-primary block border transition-colors"
  >
    <div
      class="card-body flex-col gap-3 p-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between"
    >
      <div class="flex min-w-0 flex-col gap-1">
        <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <h2 id="quality-strip-title" class="text-sm font-semibold">
            Dados até {date(meta.as_of)}
          </h2>
          <span class="text-base-content/70 text-xs">
            A CVM consolida o informe com 2 a 3 dias úteis de atraso.
          </span>
        </div>
        <p class="text-base-content/70 text-xs">
          Último dia completo do informe diário · gerado em {datetime(meta.generated_at)} ·
          {integer(meta.quality.checked_series)} séries · {integer(meta.quality.checked_days)} pares série × dia útil verificados
        </p>
        <SourceDates sources={meta.sources} class="text-base-content/70 text-xs" />
      </div>
      <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div class="flex flex-wrap items-center gap-x-2 gap-y-1.5">
          <span id="quality-strip-open" class="text-sm font-medium">Abertos:</span>
          <ul class="flex flex-wrap items-center gap-1.5" aria-labelledby="quality-strip-open">
            {#each openCounts as entry (entry.severity)}
              <li
                class={[
                  "badge badge-sm tabular-nums",
                  entry.count > 0 && SEVERITY_BADGE_CLASS[entry.severity],
                ]}
              >
                {integer(entry.count)}
                {severityCountWord(entry.severity, entry.count)}
              </li>
            {/each}
          </ul>
          <span class="text-base-content/70 text-xs tabular-nums">{treatedLine}</span>
        </div>
        <span class="text-primary text-sm font-medium">Ver alertas →</span>
      </div>
    </div>
  </a>
</section>
