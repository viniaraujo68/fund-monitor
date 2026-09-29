import { RULES } from "$lib/issues";
import { GENERAL_PUBLIC, countsAsOpen } from "$lib/labels";
import { aggregates, funds, meta, quality } from "$lib/server/site-data";
import type { PageServerLoad } from "./$types";

export interface RuleOutcome {
  rule: string;
  total: number;
  open: number;
  explained: number;
  sourceError: number;
  limitation: number;
  info: number;
}

const ruleOutcome = (rule: string): RuleOutcome => {
  const issues = quality.issues.filter((issue) => issue.rule === rule);
  const treated = (status: string) => issues.filter((issue) => issue.status === status).length;
  return {
    rule,
    total: issues.length,
    open: issues.filter((issue) => countsAsOpen(issue.status, issue.severity)).length,
    explained: treated("explained"),
    sourceError: treated("source_error"),
    limitation: treated("limitation"),
    info: issues.filter((issue) => issue.severity === "info" && issue.status === "open").length,
  };
};

const totalNetAssets = (scope: string): number =>
  aggregates.totals.find((total) => total.scope === scope && total.structural)?.net_assets ?? 0;

export const load: PageServerLoad = () => {
  const ranked = funds.filter(
    (fund) =>
      fund.target_audience === GENERAL_PUBLIC &&
      !fund.structural_vehicle &&
      fund.excess_primary_12m !== null,
  );
  const managerAssets = totalNetAssets("manager");
  return {
    meta,
    benchmark: {
      beat: ranked.filter((fund) => (fund.excess_primary_12m ?? 0) > 0).length,
      ranked: ranked.length,
    },
    exclusiveShare: managerAssets > 0 ? 1 - totalNetAssets("monitored") / managerAssets : null,
    outcomes: RULES.map(ruleOutcome),
    openTotal: Object.values(meta.quality.open_by_severity).reduce((sum, count) => sum + count, 0),
  };
};
