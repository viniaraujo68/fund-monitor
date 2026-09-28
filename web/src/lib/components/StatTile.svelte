<script lang="ts">
  import type { Snippet } from "svelte";

  const {
    label,
    value,
    hint,
    detail,
    tone = "neutral",
    size = "md",
    children,
  }: {
    label: string;
    value: string;
    hint?: string;
    detail?: string;
    size?: "md" | "sm";
    tone?: "neutral" | "positive" | "negative" | "attention";
    children?: Snippet;
  } = $props();

  const sizeClass = $derived(
    size === "sm" ? "text-sm sm:text-base lg:text-lg" : "text-base sm:text-xl lg:text-2xl",
  );

  const toneClass = $derived(
    tone === "positive"
      ? "text-success"
      : tone === "negative"
        ? "text-error"
        : tone === "attention"
          ? "text-warning"
          : undefined,
  );
</script>

<div class="stats bg-base-100 border-base-content/10 rounded-box block border">
  <div class="stat min-w-0">
    <div class="stat-title text-base-content/70 whitespace-normal">{label}</div>
    <div
      class={["min-w-0 truncate font-medium tracking-[-0.01em] tabular-nums", sizeClass, toneClass]}
      title={detail ?? value}
    >
      {value}
    </div>
    {#if hint}
      <div class="text-base-content/70 mt-0.5 text-xs leading-snug whitespace-normal">{hint}</div>
    {/if}
    {#if children}
      <div class="mt-1 text-xs">{@render children()}</div>
    {/if}
  </div>
</div>
