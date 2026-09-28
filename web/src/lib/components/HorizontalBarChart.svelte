<script lang="ts">
  import { slotVar } from "$lib/charts/theme";

  export interface HorizontalBar {
    id: string;
    label: string;
    value: number;
    href?: string;
  }

  const {
    rows,
    formatValue,
    ariaLabel,
    slot,
  }: {
    rows: HorizontalBar[];
    formatValue: (value: number) => string;
    ariaLabel: string;
    slot: number;
  } = $props();

  const top = $derived(Math.max(...rows.map((row) => Math.abs(row.value)), 0));

  const width = (value: number): string =>
    top <= 0 ? "0%" : `${Math.max(1, (Math.abs(value) / top) * 100)}%`;
</script>

<ul class="flex flex-col gap-2.5" aria-label={ariaLabel}>
  {#each rows as row (row.id)}
    <li class="flex min-w-0 flex-col gap-1 px-1 py-1">
      <div class="flex items-baseline justify-between gap-3">
        {#if row.href === undefined}
          <span class="min-w-0 truncate text-sm" title={row.label}>{row.label}</span>
        {:else}
          <a class="link link-hover min-w-0 truncate text-sm" href={row.href} title={row.label}>
            {row.label}
          </a>
        {/if}
        <span class="shrink-0 text-sm font-medium tabular-nums">{formatValue(row.value)}</span>
      </div>
      <div class="bg-base-content/10 h-2 w-full overflow-hidden rounded-sm">
        <div
          class="h-full rounded-sm"
          style:width={width(row.value)}
          style:background-color={slotVar(slot)}
        ></div>
      </div>
    </li>
  {/each}
</ul>
