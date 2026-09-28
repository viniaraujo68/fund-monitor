<script lang="ts">
  import { FUND_SLOT } from "$lib/charts/palette";
  import { slotVar } from "$lib/charts/theme";
  import type { PeerMetric } from "$lib/data/types";
  import { percentileLabel, percentWhole } from "$lib/format";

  const {
    label,
    metric,
    format,
    reading,
    betterNote,
  }: {
    label: string;
    metric: PeerMetric;
    format: (value: number | null) => string;
    reading: (share: string) => string;
    betterNote?: string;
  } = $props();

  const MARGIN = 0.12;
  const BAND_COLOR = "color-mix(in srgb, var(--color-primary) 20%, transparent)";

  const domain = $derived.by((): [number, number] => {
    const known = [metric.p25, metric.p75, metric.value, metric.median].filter(
      (value): value is number => value !== null,
    );
    if (known.length === 0) return [0, 1];
    const low = Math.min(...known);
    const high = Math.max(...known);
    const span = high - low || Math.abs(high) || 1;
    return [low - span * MARGIN, high + span * MARGIN];
  });

  const position = (value: number | null): string | undefined => {
    if (value === null) return undefined;
    const [low, high] = domain;
    return `${((value - low) / (high - low)) * 100}%`;
  };

  const bandWidth = $derived(
    metric.p25 === null || metric.p75 === null
      ? undefined
      : `${((metric.p75 - metric.p25) / (domain[1] - domain[0])) * 100}%`,
  );

  const caption = $derived(
    [
      `Faixa central (P25 a P75): ${format(metric.p25)} a ${format(metric.p75)}`,
      metric.percentile === null ? null : reading(percentWhole(metric.percentile)),
    ]
      .filter((part) => part !== null)
      .join(" · "),
  );

  const summary = $derived(
    `${label}: fundo ${format(metric.value)}, mediana dos pares ${format(metric.median)}, faixa central de ${format(metric.p25)} a ${format(metric.p75)}, percentil ${percentileLabel(metric.percentile)}`,
  );
</script>

<div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-6">
  <div class="flex min-w-0 flex-col gap-1.5 sm:flex-1">
    <div class="flex flex-wrap items-baseline gap-x-2">
      <h3 class="text-sm font-medium">{label}</h3>
      {#if betterNote !== undefined}
        <span class="text-base-content/70 text-xs">{betterNote}</span>
      {/if}
    </div>
    <div class="relative h-6" role="img" aria-label={summary} title={summary}>
      <div class="bg-base-content/10 absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded-full"></div>
      {#if bandWidth !== undefined}
        <div
          class="absolute top-1/2 h-2 -translate-y-1/2"
          style:left={position(metric.p25)}
          style:width={bandWidth}
          style:background-color={BAND_COLOR}
        ></div>
      {/if}
      {#each [metric.p25, metric.p75] as quartile, index (index)}
        {#if quartile !== null}
          <div
            class="bg-base-content/40 absolute top-1/2 h-3 w-px -translate-y-1/2"
            style:left={position(quartile)}
          ></div>
        {/if}
      {/each}
      {#if metric.median !== null}
        <div
          class="bg-base-content/80 absolute top-1/2 h-4 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
          style:left={position(metric.median)}
        ></div>
      {/if}
      {#if metric.value !== null}
        <div
          class="border-base-100 ring-base-content/70 absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 ring-1"
          style:left={position(metric.value)}
          style:background-color={slotVar(FUND_SLOT)}
        ></div>
      {/if}
    </div>
    <p class="text-base-content/70 text-xs tabular-nums">
      {caption}
    </p>
  </div>
  <dl class="grid shrink-0 grid-cols-3 gap-3 text-sm sm:w-72">
    <div class="flex flex-col">
      <dt class="text-base-content/70 text-xs">Fundo</dt>
      <dd class="font-medium tabular-nums">{format(metric.value)}</dd>
    </div>
    <div class="flex flex-col">
      <dt class="text-base-content/70 text-xs">Mediana</dt>
      <dd class="tabular-nums">{format(metric.median)}</dd>
    </div>
    <div class="flex flex-col">
      <dt class="text-base-content/70 text-xs">Percentil</dt>
      <dd class="tabular-nums">{percentileLabel(metric.percentile)}</dd>
    </div>
  </dl>
</div>
