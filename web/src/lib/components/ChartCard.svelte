<script lang="ts">
  import type { Snippet } from "svelte";

  const {
    title,
    note,
    empty,
    actions,
    chart,
    table,
  }: {
    title: string;
    note?: string;
    empty?: string;
    actions?: Snippet;
    chart: Snippet;
    table: Snippet;
  } = $props();

  let showTable = $state(false);
</script>

<section class="card bg-base-100 border-base-content/10 border">
  <div class="card-body gap-4 p-4 sm:p-5">
    <div class="flex flex-col gap-1">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-base font-semibold">{title}</h2>
        <div class="flex flex-wrap items-center gap-2">
          {#if actions}{@render actions()}{/if}
          {#if empty === undefined}
            <button
              type="button"
              class="btn btn-ghost btn-sm"
              aria-pressed={showTable}
              onclick={() => (showTable = !showTable)}
            >
              {showTable ? "Ver gráfico" : "Ver tabela"}
            </button>
          {/if}
        </div>
      </div>
      {#if note}
        <p class="text-base-content/70 text-xs">{note}</p>
      {/if}
    </div>

    {#if empty !== undefined}
      <p class="text-base-content/70 py-8 text-center text-sm">{empty}</p>
    {:else if showTable}
      <div class="overflow-x-auto">{@render table()}</div>
    {:else}
      {@render chart()}
    {/if}
  </div>
</section>
