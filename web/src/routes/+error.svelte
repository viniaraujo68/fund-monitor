<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/state";

  const notFound = $derived(page.status === 404);
</script>

<svelte:head>
  <title>{notFound ? "Página não encontrada" : "Algo deu errado"} · Monitor de fundos</title>
</svelte:head>

<div class="flex h-full w-full flex-col items-center justify-center gap-2 p-8 text-center">
  <svg
    class="text-base-content/40 size-12"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    {#if notFound}
      <path d="m16.24 7.76-1.8 5.41a2 2 0 0 1-1.27 1.27l-5.41 1.8 1.8-5.41a2 2 0 0 1 1.27-1.27z" />
      <circle cx="12" cy="12" r="10" />
    {:else}
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    {/if}
  </svg>
  <p class="text-base-content/70 text-xs font-medium tracking-widest uppercase">
    Erro {page.status}
  </p>
  <h1 class="text-xl font-semibold">
    {notFound ? "Página não encontrada" : "Algo deu errado"}
  </h1>
  <p class="text-base-content/70 max-w-md text-sm">
    {#if notFound}
      O endereço <span class="font-mono break-all">{page.url.pathname}</span> não existe ou mudou de
      lugar.
    {:else}
      {page.error?.message ?? "O site encontrou um problema inesperado."}
    {/if}
  </p>
  <div class="mt-4 flex flex-wrap justify-center gap-2">
    <a class="btn btn-primary" href={resolve("/")}>Voltar à visão geral</a>
  </div>
</div>
