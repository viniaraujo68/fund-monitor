<script lang="ts">
  import type { Snippet } from "svelte";

  const {
    title,
    note,
    chart,
    table,
  }: {
    title: string;
    note?: string;
    chart: Snippet;
    table: Snippet;
  } = $props();

  const titleId = $props.id();

  let showTable = $state(false);
</script>

<section class="card bg-base-100 border-base-content/10 border" aria-labelledby={titleId}>
  <div class="card-body gap-4 p-4 sm:p-5">
    <div class="flex flex-col gap-1">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 id={titleId} class="text-base font-semibold">{title}</h2>
        <button type="button" class="btn btn-ghost btn-sm" onclick={() => (showTable = !showTable)}>
          {showTable ? "Ver gráfico" : "Ver tabela"}
        </button>
      </div>
      {#if note}
        <p class="text-base-content/70 text-xs">{note}</p>
      {/if}
    </div>

    {#if showTable}
      <div class="overflow-x-auto">{@render table()}</div>
    {:else}
      {@render chart()}
    {/if}
  </div>
</section>
