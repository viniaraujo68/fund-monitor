<script lang="ts">
  import type { Meta } from "$lib/data/types";
  import { date, datetime, integer } from "$lib/format";
  import { SEVERITIES, severityCountWord, sourceLabel, type Severity } from "$lib/labels";

  const { meta }: { meta: Meta } = $props();

  const BADGE_CLASS: Record<Severity, string> = {
    high: "badge-error",
    medium: "badge-warning",
    low: "",
    info: "",
  };

  const severities = $derived(
    SEVERITIES.map((severity) => ({
      severity,
      count: meta.quality.by_severity[severity] ?? 0,
    })),
  );
</script>

<section
  class="card bg-base-100 border-base-content/10 border"
  aria-labelledby="quality-strip-title"
>
  <div class="card-body flex-col gap-3 p-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
    <div class="flex min-w-0 flex-col gap-1">
      <h2 id="quality-strip-title" class="text-sm font-semibold">
        Dados até {date(meta.as_of)}
      </h2>
      <p class="text-base-content/70 text-xs">
        Último dia completo do informe diário · gerado em {datetime(meta.generated_at)} ·
        {integer(meta.quality.checked_series)} séries · {integer(meta.quality.checked_days)} dias verificados
      </p>
      <ul class="text-base-content/70 flex flex-wrap gap-x-3 gap-y-1 text-xs" aria-label="Fontes">
        {#each meta.sources as source (source.source)}
          <li>
            {sourceLabel(source.source)}:
            <span class="tabular-nums">{date(source.last_date)}</span>
          </li>
        {/each}
      </ul>
    </div>
    <ul class="flex flex-wrap items-center gap-1.5" aria-label="Alertas de qualidade por severidade">
      {#each severities as entry (entry.severity)}
        <li class={["badge badge-sm tabular-nums", BADGE_CLASS[entry.severity]]}>
          {integer(entry.count)}
          {severityCountWord(entry.severity, entry.count)}
        </li>
      {/each}
    </ul>
  </div>
</section>
