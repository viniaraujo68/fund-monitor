import { buildHighlights } from "$lib/highlights";
import { aggregates, funds, meta, quality } from "$lib/server/site-data";
import type { PageServerLoad } from "./$types";

const MONTHLY_GROUP = "cvm_classification";

export const load: PageServerLoad = () => ({
  meta,
  funds,
  totals: aggregates.totals,
  monthly: aggregates.monthly.filter((row) => row.group === MONTHLY_GROUP),
  highlights: buildHighlights(funds, quality, meta),
});
