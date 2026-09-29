<script lang="ts">
  import { Tooltip } from "@viniaraujo68/plinth/components";
  import { triageDetail } from "$lib/issues";
  import { statusLabel } from "$lib/labels";

  const {
    status,
    note = null,
    treatedOn = null,
  }: { status: string; note?: string | null; treatedOn?: string | null } = $props();

  const tip = $derived(triageDetail(note, treatedOn));

  const badgeClass = $derived([
    "badge badge-sm shrink-0",
    status === "open" ? "badge-primary" : "badge-outline",
  ]);
</script>

{#if tip === ""}
  <span class={badgeClass}>{statusLabel(status)}</span>
{:else}
  <Tooltip class={[badgeClass, "cursor-help"]} aria-label={`${statusLabel(status)}: ${tip}`}>
    {statusLabel(status)}
    {#snippet tooltip()}
      <span class="block max-w-72 text-xs">{tip}</span>
    {/snippet}
  </Tooltip>
{/if}
