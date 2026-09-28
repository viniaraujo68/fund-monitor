import aggregatesJson from "$data/aggregates.json";
import fundsJson from "$data/funds.json";
import metaJson from "$data/meta.json";
import qualityJson from "$data/quality.json";
import type { Aggregates, FundDetail, FundSummary, Meta, QualityDocument } from "$lib/data/types";

export const meta = metaJson as Meta;

export const funds = fundsJson as FundSummary[];

export const aggregates = aggregatesJson as Aggregates;

export const quality = qualityJson as QualityDocument;

const detailFiles = import.meta.glob<FundDetail>("$data/funds/*.json", {
  eager: true,
  import: "default",
});

const details = new Map(
  Object.values(detailFiles).map((detail) => [detail.summary.series_id, detail]),
);

export const fundDetail = (seriesId: string): FundDetail | undefined => details.get(seriesId);
