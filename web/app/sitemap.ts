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
  "/methodology/",
  "/submit/",
] as const;

export const dynamic = "force-static";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [index, runParams] = await Promise.all([getIndexData(), getSitemapRunStaticParams()]);
  const paths = [
    ...STATIC_PATHS,
    ...familySummaries(index.models).map((summary) => `/families/${summary.slug}/`),
    ...index.models.map((model) => `/model/${model.slug}/`),
    ...runParams.map((param) => `/run/${param.runId}/`),
  ];
  return paths.map((path) => ({ url: absoluteUrl(path) }));
}

function absoluteUrl(path: string): string {
  return new URL(path, SITE_URL).toString();
}
