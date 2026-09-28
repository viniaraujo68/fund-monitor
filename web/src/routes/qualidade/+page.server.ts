import { funds, meta, quality } from "$lib/server/site-data";
import type { PageServerLoad } from "./$types";

export const load: PageServerLoad = () => ({
  meta,
  quality,
  fundIds: funds.map((fund) => fund.series_id),
});
