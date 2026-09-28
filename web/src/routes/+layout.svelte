<script lang="ts">
  import "./layout.css";
  import type { Snippet } from "svelte";
  import { browser } from "$app/environment";
  import { page } from "$app/state";
  import {
    RoutingContext,
    setRoutingContext,
    type ResolvedRoute,
  } from "@viniaraujo68/plinth/routing";
  import { AppShell } from "@viniaraujo68/plinth/shell";
  import {
    readThemePreference,
    setThemeContext,
    ThemeContext,
    ThemeController,
    ThemeToggle,
    type ThemePreference,
  } from "@viniaraujo68/plinth/theme";
  import { iconPaths } from "$lib/icons";
  import { routes } from "$lib/routes";

  const { children }: { children: Snippet } = $props();

  setThemeContext(new ThemeContext(browser ? readThemePreference() : "system"));
  setRoutingContext(new RoutingContext(routes, page));

  const THEME_LABELS: Record<ThemePreference, string> = {
    system: "Sistema",
    light: "Claro",
    dark: "Escuro",
  };

  const themePreferenceLabel = (preference: ThemePreference): string => THEME_LABELS[preference];

  const themeLabel = (current: ThemePreference, next: ThemePreference): string =>
    `Tema: ${THEME_LABELS[current]}. Mudar para ${THEME_LABELS[next]}.`;
</script>

<ThemeController />

<a
  href="#conteudo"
  class="btn btn-primary btn-sm sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50"
>
  Pular para o conteúdo
</a>

<div class="h-dvh">
  <AppShell
    navLabel="Navegação principal"
    collapseLabel="Recolher menu"
    moreLabel="Mais"
    closeLabel="Fechar"
    logoutLabel="Sair"
  >
    {#snippet brand({ collapsed }: { collapsed: boolean })}
      <span class="text-lg font-bold tracking-tight">{collapsed ? "MF" : "Monitor de fundos"}</span>
    {/snippet}

    {#snippet icon(route: ResolvedRoute)}
      <svg
        class="size-5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.75"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        {#each iconPaths(route.meta.icon) as d (d)}
          <path {d} />
        {/each}
      </svg>
    {/snippet}

    {#snippet footer()}
      <ThemeToggle iconOnly preferenceLabel={themePreferenceLabel} label={themeLabel} />
    {/snippet}

    {@render children()}
  </AppShell>
</div>
