<script lang="ts">
  import PageFrame from "$lib/components/PageFrame.svelte";

  const { data } = $props();

  const rendered = $derived(data.document);
</script>

{#snippet article()}
  <article class="methodology card bg-base-100 border-base-content/10 min-w-0 border p-4 sm:p-6">
    {@html rendered.html}
  </article>
{/snippet}

<PageFrame
  title="Metodologia"
  description="Decisões de método: fontes, universo, cálculos, pares e regras de qualidade."
  wide
>
  {#if rendered.headings.length > 0}
    <div class="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <nav aria-labelledby="index-title" class="lg:sticky lg:top-4 lg:self-start">
        <div class="card bg-base-100 border-base-content/10 border">
          <div class="card-body gap-2 p-4">
            <h2 id="index-title" class="text-sm font-semibold">Nesta página</h2>
            <ol class="flex flex-col gap-1 text-sm">
              {#each rendered.headings as heading (heading.id)}
                <li>
                  <a class="link link-hover text-base-content/80 block py-0.5" href={`#${heading.id}`}>
                    {heading.text}
                  </a>
                </li>
              {/each}
            </ol>
          </div>
        </div>
      </nav>
      {@render article()}
    </div>
  {:else}
    {@render article()}
  {/if}
</PageFrame>

<style>
  .methodology {
    font-size: 0.9375rem;
    line-height: 1.65;
    overflow-wrap: break-word;
  }

  .methodology > :global(* + *) {
    margin-top: 0.875rem;
  }

  .methodology :global(h2) {
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid color-mix(in oklab, var(--color-base-content) 10%, transparent);
    font-size: 1.125rem;
    font-weight: 600;
    line-height: 1.35;
    scroll-margin-top: 1rem;
  }

  .methodology > :global(h2:first-child) {
    margin-top: 0;
    padding-top: 0;
    border-top: 0;
  }

  .methodology :global(h3) {
    margin-top: 1.5rem;
    font-size: 1rem;
    font-weight: 600;
    scroll-margin-top: 1rem;
  }

  .methodology :global(h4) {
    margin-top: 1.25rem;
    font-weight: 600;
  }

  .methodology :global(ul),
  .methodology :global(ol) {
    padding-left: 1.25rem;
  }

  .methodology :global(ul) {
    list-style: disc;
  }

  .methodology :global(ol) {
    list-style: decimal;
  }

  .methodology :global(li + li) {
    margin-top: 0.25rem;
  }

  .methodology :global(li > ul),
  .methodology :global(li > ol) {
    margin-top: 0.25rem;
  }

  .methodology :global(a) {
    color: var(--color-primary);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .methodology :global(strong) {
    font-weight: 600;
  }

  .methodology :global(code) {
    padding: 0.1em 0.35em;
    border-radius: 0.25rem;
    background: color-mix(in oklab, var(--color-base-content) 8%, transparent);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.85em;
  }

  .methodology :global(pre) {
    overflow-x: auto;
    padding: 0.75rem 1rem;
    border-radius: var(--radius-box);
    background: var(--color-base-200);
    font-size: 0.8125rem;
    line-height: 1.5;
  }

  .methodology :global(pre code) {
    padding: 0;
    background: transparent;
    font-size: inherit;
  }

  .methodology :global(blockquote) {
    padding-left: 1rem;
    border-left: 3px solid color-mix(in oklab, var(--color-base-content) 20%, transparent);
    color: color-mix(in oklab, var(--color-base-content) 80%, transparent);
  }

  .methodology :global(hr) {
    border-color: color-mix(in oklab, var(--color-base-content) 10%, transparent);
  }

  .methodology :global(table) {
    min-width: 36rem;
    font-size: 0.8125rem;
  }

  .methodology :global(th) {
    white-space: nowrap;
  }
</style>
