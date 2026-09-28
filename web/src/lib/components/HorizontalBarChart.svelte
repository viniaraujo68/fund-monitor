<script lang="ts">
  import { slotVar } from "$lib/charts/theme";

  export interface HorizontalBar {
    id: string;
    label: string;
    value: number;
    hint?: string;
  }

  const {
    rows,
    formatValue,
    ariaLabel,
    limit = 8,
    positiveSlot = 1,
    negativeSlot = 4,
    otherLabel = "Outros",
    otherHint = (count: number) => `${count} ${count === 1 ? "item" : "itens"}`,
  }: {
    rows: HorizontalBar[];
    formatValue: (value: number) => string;
    ariaLabel: string;
    limit?: number;
    positiveSlot?: number;
    negativeSlot?: number;
    otherLabel?: string;
    otherHint?: (count: number) => string;
  } = $props();

  const OTHER_ID = "__other__";

  const ranked = $derived([...rows].sort((a, b) => b.value - a.value));

  const bars = $derived.by((): HorizontalBar[] => {
    if (ranked.length <= limit) return ranked;
    const head = ranked.slice(0, limit);
    const tail = ranked.slice(limit);
    return [
      ...head,
      {
        id: OTHER_ID,
        label: otherLabel,
        value: tail.reduce((sum, row) => sum + row.value, 0),
        hint: otherHint(tail.length),
      },
    ];
  });

  const top = $derived(Math.max(...bars.map((bar) => Math.abs(bar.value)), 0));

  const width = (value: number): string =>
    top <= 0 ? "0%" : `${Math.max(1, (Math.abs(value) / top) * 100)}%`;

  const barColor = (value: number): string => slotVar(value < 0 ? negativeSlot : positiveSlot);
</script>

<ul class="flex flex-col gap-2.5" aria-label={ariaLabel}>
  {#each bars as row (row.id)}
    <li class="flex min-w-0 flex-col gap-1 px-1 py-1">
      <div class="flex items-baseline justify-between gap-3">
        <span class="min-w-0 truncate text-sm" title={row.label}>{row.label}</span>
        <span class="shrink-0 text-sm font-medium tabular-nums">{formatValue(row.value)}</span>
      </div>
      <div class="bg-base-content/10 h-2 w-full overflow-hidden rounded-sm">
        <div
          class="h-full rounded-sm"
          style:width={width(row.value)}
          style:background-color={barColor(row.value)}
        ></div>
      </div>
      {#if row.hint !== undefined}
        <span class="text-base-content/70 text-xs">{row.hint}</span>
      {/if}
    </li>
  {/each}
</ul>
