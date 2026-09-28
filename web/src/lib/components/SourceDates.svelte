<script lang="ts">
  import type { ClassValue } from "svelte/elements";
  import type { SourceStatus } from "$lib/data/types";
  import { date } from "$lib/format";
  import { sourceLabel } from "$lib/labels";

  const { sources, class: className }: { sources: SourceStatus[]; class?: ClassValue } = $props();
</script>

<ul class={["flex flex-wrap gap-x-3 gap-y-1", className]} aria-label="Fontes">
  {#each sources as source (source.source)}
    <li>
      {sourceLabel(source.source)}:
      <span class="tabular-nums">{date(source.last_date)}</span>
    </li>
  {/each}
</ul>
