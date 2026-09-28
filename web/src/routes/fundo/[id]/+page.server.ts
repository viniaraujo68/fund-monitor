import { error } from "@sveltejs/kit";
import { fundDetail, funds, meta } from "$lib/server/site-data";
import type { EntryGenerator, PageServerLoad } from "./$types";

export const entries: EntryGenerator = () => funds.map((fund) => ({ id: fund.series_id }));

export const load: PageServerLoad = ({ params }) => {
  const detail = fundDetail(params.id);
  if (detail === undefined) error(404, "Fundo não encontrado");
  return { detail, meta };
};
