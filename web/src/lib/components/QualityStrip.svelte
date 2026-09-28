<script lang="ts">
  import { resolve } from "$app/paths";
  import type { Meta } from "$lib/data/types";
  import { date, datetime, integer } from "$lib/format";
  import { SEVERITIES, SEVERITY_BADGE_CLASS, severityCountWord } from "$lib/labels";
  import SourceDates from "./SourceDates.svelte";

  const { meta }: { meta: Meta } = $props();

  const severities = $derived(
    SEVERITIES.map((severity) => ({
      severity,
      count: meta.quality.by_severity[severity] ?? 0,
    })),
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
        <h2 id="quality-strip-title" class="text-sm font-semibold">
          Dados até {date(meta.as_of)}
        </h2>
        <p class="text-base-content/70 text-xs">
          Último dia completo do informe diário · gerado em {datetime(meta.generated_at)} ·
          {integer(meta.quality.checked_series)} séries · {integer(meta.quality.checked_days)} pares série × dia útil verificados
        </p>
        <SourceDates sources={meta.sources} class="text-base-content/70 text-xs" />
      </div>
      <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
        <ul class="flex flex-wrap items-center gap-1.5" aria-label="Alertas de qualidade por severidade">
          {#each severities as entry (entry.severity)}
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
        <span class="text-primary text-sm font-medium">Ver alertas →</span>
      </div>
    </div>
  </a>
</section>
