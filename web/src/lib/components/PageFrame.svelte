<script lang="ts">
  import type { Snippet } from "svelte";
  import { Breadcrumbs } from "@viniaraujo68/plinth/shell";

  const {
    title,
    description,
    header,
    actions,
    children,
    breadcrumbs = true,
    wide = false,
  }: {
    title: string;
    description?: string;
    header?: Snippet;
    actions?: Snippet;
    children: Snippet;
    breadcrumbs?: boolean;
    wide?: boolean;
  } = $props();
</script>

<svelte:head>
  <title>{title} · Monitor de fundos</title>
</svelte:head>

<div class={["mx-auto flex w-full flex-col gap-6 p-4 sm:p-6", wide ? "max-w-7xl" : "max-w-5xl"]}>
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div class="flex min-w-0 flex-col gap-1">
      {#if breadcrumbs}
        <Breadcrumbs label="Trilha de navegação" />
      {/if}
      <h1 class="text-xl font-semibold tracking-tight">{title}</h1>
      {#if description}
        <p class="text-base-content/70 text-sm">{description}</p>
      {/if}
      {#if header}{@render header()}{/if}
    </div>
    {#if actions}
      <div class="flex flex-wrap items-center gap-2">{@render actions()}</div>
    {/if}
  </div>
  <div id="conteudo" tabindex="-1" class="flex flex-col gap-6 outline-none">
    {@render children()}
  </div>
</div>

<style>
  @container plinth-table (max-width: 40rem) {
    #conteudo :global(.plinth-table.has-card thead) {
      display: none;
    }
  }
</style>
