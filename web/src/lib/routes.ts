import type { RouteId } from "$app/types";
import type { RoutingConfig } from "@viniaraujo68/plinth/routing";

export const routes: RoutingConfig<RouteId> = {
  meta: {
    "/": { title: "Visão geral", icon: "overview" },
    "/qualidade": { title: "Qualidade", icon: "shield" },
    "/como-funciona": { title: "Como funciona", icon: "book" },
    "/fundo/[id]": { title: "Fundo" },
  },

  pages: import.meta.glob("/src/routes/**/+page.svelte"),
};
