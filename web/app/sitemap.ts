import type { MetadataRoute } from "next";
import { getIndexData, getSitemapRunStaticParams } from "@/lib/data";
import { familySummaries } from "@/lib/families";

const SITE_URL = "https://local-bench.ai";
const STATIC_PATHS = [
  "/",
  "/families/",
  "/leaderboard/",
  "/submissions/",
  "/submission/",
  "/compare/",
  "/feedback/",
  "/methodology/",
  "/submit/",
] as const;

export const dynamic = "force-static";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [index, runParams] = await Promise.all([getIndexData(), getSitemapRunStaticParams()]);
  return [
    ...STATIC_PATHS.map((path) => ({ url: absoluteUrl(path) })),
    ...familySummaries(index.models).map((summary) => datedEntry(`/families/${summary.slug}/`, index.generated_at)),
    ...index.models.map((model) => datedEntry(`/model/${model.slug}/`, index.generated_at)),
    ...runParams.map((param) => ({ url: absoluteUrl(`/run/${param.runId}/`) })),
  ];
}

function datedEntry(path: string, lastModified: string | undefined): MetadataRoute.Sitemap[number] {
  return lastModified === undefined
    ? { url: absoluteUrl(path) }
    : { url: absoluteUrl(path), lastModified };
}

function absoluteUrl(path: string): string {
  return new URL(path, SITE_URL).toString();
}
