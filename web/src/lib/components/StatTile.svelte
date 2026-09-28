<script lang="ts">
  type Tone = "neutral" | "positive" | "negative" | "attention";

  const {
    label,
    value,
    hint,
    detail,
    tone = "neutral",
  }: {
    label: string;
    value: string;
    hint?: string;
    detail?: string;
    tone?: Tone;
  } = $props();

  const TONE_CLASS: Record<Tone, string | undefined> = {
    neutral: undefined,
    positive: "text-success",
    negative: "text-error",
    attention: "text-warning",
  };
</script>

<div class="stats bg-base-100 border-base-content/10 rounded-box block border">
  <div class="stat min-w-0">
    <div class="stat-title text-base-content/70 whitespace-normal">{label}</div>
    <div
      class={[
        "min-w-0 truncate text-base font-medium tracking-[-0.01em] tabular-nums sm:text-xl lg:text-2xl",
        TONE_CLASS[tone],
      ]}
      title={detail ?? value}
    >
      {value}
    </div>
    {#if hint}
      <div class="text-base-content/70 mt-0.5 text-xs leading-snug whitespace-normal">{hint}</div>
    {/if}
  </div>
</div>
