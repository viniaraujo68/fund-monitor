import { decisions } from "$lib/server/docs";
import { renderMarkdown } from "$lib/server/markdown";
import type { PageServerLoad } from "./$types";

export const load: PageServerLoad = () => ({
  document: renderMarkdown(decisions),
});
